import * as vscode from "vscode";
import { execFile } from "child_process";
import { promisify } from "util";

const run = promisify(execFile);

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

/** Find the `bb` executable. Prefer workspace python, fall back to PATH. */
async function findBb(): Promise<string> {
  // Check user setting first
  const cfg = vscode.workspace.getConfiguration("briefbridge");
  const explicit = cfg.get<string>("bbPath");
  if (explicit) return explicit;

  // Default: assume `bb` is on PATH (pip install -e . puts it there)
  return "bb";
}

interface BbResult {
  stdout: string;
  stderr: string;
  ok: boolean;
}

async function bb(args: string[], token?: vscode.CancellationToken): Promise<BbResult> {
  const bin = await findBb();
  try {
    const { stdout, stderr } = await run(bin, args, {
      timeout: 30_000,
      maxBuffer: 4 * 1024 * 1024,
      windowsHide: true,
    });
    return { stdout: stdout.trim(), stderr: stderr.trim(), ok: true };
  } catch (err: any) {
    return {
      stdout: err.stdout?.trim() ?? "",
      stderr: err.stderr?.trim() ?? err.message ?? "unknown error",
      ok: false,
    };
  }
}

/* ------------------------------------------------------------------ */
/*  Session picker                                                     */
/* ------------------------------------------------------------------ */

interface SessionInfo {
  id: string;
  provider: string;
  started_at: string | null;
  repo_name: string | null;
  branch: string | null;
  title: string | null;
  files_touched: number;
}

async function pickSession(
  provider?: string,
  token?: vscode.CancellationToken
): Promise<string | undefined> {
  const args = ["sessions", "--json"];
  if (provider) args.push("--provider", provider);
  const res = await bb(args, token);
  if (!res.ok) {
    vscode.window.showErrorMessage(`bb sessions failed: ${res.stderr}`);
    return undefined;
  }
  let sessions: SessionInfo[];
  try {
    sessions = JSON.parse(res.stdout);
  } catch {
    vscode.window.showErrorMessage("Failed to parse sessions JSON");
    return undefined;
  }
  if (sessions.length === 0) {
    vscode.window.showInformationMessage("No sessions found.");
    return undefined;
  }

  const items = sessions.map((s) => ({
    label: s.id,
    description: s.provider,
    detail: [
      s.started_at?.substring(0, 16),
      s.repo_name,
      s.title?.substring(0, 60),
    ]
      .filter(Boolean)
      .join(" · "),
  }));

  const pick = await vscode.window.showQuickPick(items, {
    placeHolder: "Select a session",
    matchOnDescription: true,
    matchOnDetail: true,
  });
  return pick?.label;
}

/* ------------------------------------------------------------------ */
/*  Markdown formatters                                                */
/* ------------------------------------------------------------------ */

function formatSessionsTable(sessions: SessionInfo[]): string {
  if (sessions.length === 0) return "*No sessions found.*";
  const lines = [
    "| ID | Provider | Time | Repo | Files |",
    "|---|---|---|---|---|",
  ];
  for (const s of sessions.slice(0, 50)) {
    const time = s.started_at?.substring(0, 16) ?? "-";
    const repo = s.repo_name ?? "-";
    const id = `\`${s.id}\``;
    lines.push(`| ${id} | ${s.provider} | ${time} | ${repo} | ${s.files_touched} |`);
  }
  if (sessions.length > 50) {
    lines.push(`\n*... and ${sessions.length - 50} more sessions.*`);
  }
  return lines.join("\n");
}

function formatInspect(raw: string): string {
  // The inspect --json gives us a dict — format it nicely
  try {
    const d = JSON.parse(raw);
    const lines: string[] = [];
    lines.push(`## Session: \`${d.id}\``);
    lines.push("");
    lines.push(`- **Provider:** ${d.provider}`);
    if (d.started_at) lines.push(`- **Started:** ${d.started_at}`);
    if (d.ended_at) lines.push(`- **Ended:** ${d.ended_at}`);
    if (d.repo_name) lines.push(`- **Repo:** ${d.repo_name}`);
    if (d.branch) lines.push(`- **Branch:** ${d.branch}`);
    lines.push(`- **Messages:** ${d.message_count}`);
    lines.push(`- **Commands:** ${d.command_count}`);
    if (d.first_user_message) {
      lines.push("");
      lines.push("**First message:**");
      lines.push(`> ${d.first_user_message.substring(0, 300)}`);
    }
    if (d.files_touched?.length) {
      lines.push("");
      lines.push("**Files touched:**");
      for (const f of d.files_touched.slice(0, 20)) {
        lines.push(`- \`${f}\``);
      }
    }
    if (d.error_hints?.length) {
      lines.push("");
      lines.push("**Errors:**");
      for (const e of d.error_hints.slice(0, 10)) {
        lines.push(`- ${e}`);
      }
    }
    return lines.join("\n");
  } catch {
    return raw;
  }
}

/* ------------------------------------------------------------------ */
/*  Chat handler                                                       */
/* ------------------------------------------------------------------ */

const handler: vscode.ChatRequestHandler = async (
  request: vscode.ChatRequest,
  context: vscode.ChatContext,
  stream: vscode.ChatResponseStream,
  token: vscode.CancellationToken
): Promise<vscode.ChatResult> => {
  const command = request.command;
  const query = request.prompt.trim();

  // ------ /sessions ------
  if (command === "sessions") {
    stream.progress("Scanning sessions...");
    const provider = query || undefined; // e.g. "@bb /sessions claude"
    const args = ["sessions", "--json"];
    if (provider) args.push("--provider", provider);
    const res = await bb(args, token);
    if (!res.ok) {
      stream.markdown(`**Error:** ${res.stderr}`);
      return {};
    }
    let sessions: SessionInfo[];
    try {
      sessions = JSON.parse(res.stdout);
    } catch {
      stream.markdown("Failed to parse sessions.");
      return {};
    }
    stream.markdown(formatSessionsTable(sessions));
    return {};
  }

  // ------ /inspect ------
  if (command === "inspect") {
    let sessionId = query;
    if (!sessionId) {
      sessionId = (await pickSession(undefined, token)) ?? "";
    }
    if (!sessionId) {
      stream.markdown("No session selected.");
      return {};
    }
    stream.progress(`Inspecting ${sessionId}...`);
    const res = await bb(["inspect", sessionId, "--json"], token);
    if (!res.ok) {
      stream.markdown(`**Error:** ${res.stderr}`);
      return {};
    }
    stream.markdown(formatInspect(res.stdout));
    return {};
  }

  // ------ /use ------
  if (command === "use") {
    // Parse: "<session_id> [mode]" or just pick
    const parts = query.split(/\s+/);
    let sessionId = parts[0] || "";
    const mode = parts[1] || "compact";

    if (!sessionId || !sessionId.includes(":")) {
      sessionId = (await pickSession(undefined, token)) ?? "";
    }
    if (!sessionId) {
      stream.markdown("No session selected.");
      return {};
    }
    stream.progress(`Generating handoff (${mode})...`);
    const res = await bb(["use", sessionId, "--mode", mode], token);
    if (!res.ok) {
      stream.markdown(`**Error:** ${res.stderr}`);
      return {};
    }
    stream.markdown("```\n" + res.stdout + "\n```");
    stream.markdown(
      "\n*Copy the block above and paste it into the other agent as context.*"
    );
    return {};
  }

  // ------ /pack ------
  if (command === "pack") {
    let sessionId = query;
    if (!sessionId || !sessionId.includes(":")) {
      sessionId = (await pickSession(undefined, token)) ?? "";
    }
    if (!sessionId) {
      stream.markdown("No session selected.");
      return {};
    }
    stream.progress(`Packing ${sessionId}...`);
    const res = await bb(["pack", sessionId, "--json"], token);
    if (!res.ok) {
      stream.markdown(`**Error:** ${res.stderr}`);
      return {};
    }
    try {
      const pack = JSON.parse(res.stdout);
      const lines: string[] = [];
      lines.push(`## Handoff Pack: \`${pack.handoff_id}\``);
      lines.push("");
      if (pack.objective) lines.push(`**Objective:** ${pack.objective}`);
      lines.push(`**Files:** ${pack.relevant_files?.length ?? 0}`);
      lines.push(`**Errors:** ${pack.errors_found?.length ?? 0}`);
      lines.push(`**Commands:** ${pack.important_commands?.length ?? 0}`);
      lines.push(`**Pending:** ${pack.pending_items?.length ?? 0}`);
      lines.push("");
      lines.push(
        `Use \`@bb /use ${sessionId}\` to get a paste-ready handoff block.`
      );
      stream.markdown(lines.join("\n"));
    } catch {
      stream.markdown(res.stdout);
    }
    return {};
  }

  // ------ Default (no command) ------
  // Natural language — try to be helpful
  if (!query) {
    stream.markdown(
      [
        "**BriefBridge** — cross-agent session handoff\n",
        "Commands:",
        "- `@bb /sessions` — list all sessions",
        "- `@bb /sessions claude` — filter by provider",
        "- `@bb /inspect <session_id>` — session details",
        "- `@bb /use <session_id>` — paste-ready handoff block",
        "- `@bb /pack <session_id>` — full handoff pack",
        "",
        "Or just ask a question about a session, e.g.:",
        "- `@bb what was my last Claude session about?`",
      ].join("\n")
    );
    return {};
  }

  // Try keyword-based search: find sessions, pick best match
  stream.progress("Searching sessions...");
  const res = await bb(["sessions", "--json"], token);
  if (!res.ok) {
    stream.markdown(`**Error:** ${res.stderr}`);
    return {};
  }

  let sessions: SessionInfo[];
  try {
    sessions = JSON.parse(res.stdout);
  } catch {
    stream.markdown("Failed to load sessions.");
    return {};
  }

  // Simple keyword match on provider/repo/title
  const q = query.toLowerCase();
  const providerHint = ["claude", "codex", "copilot"].find((p) => q.includes(p));
  let filtered = sessions;
  if (providerHint) {
    filtered = sessions.filter((s) => s.provider === providerHint);
  }

  if (filtered.length === 0) {
    stream.markdown("No matching sessions found.");
    return {};
  }

  // Show top results
  stream.markdown(formatSessionsTable(filtered.slice(0, 10)));
  stream.markdown(
    `\nUse \`@bb /inspect <id>\` or \`@bb /use <id>\` to continue.`
  );
  return {};
};

/* ------------------------------------------------------------------ */
/*  Activation                                                         */
/* ------------------------------------------------------------------ */

export function activate(context: vscode.ExtensionContext) {
  const participant = vscode.chat.createChatParticipant(
    "briefbridge.bb",
    handler
  );
  participant.iconPath = new vscode.ThemeIcon("arrow-swap");
  context.subscriptions.push(participant);
}

export function deactivate() {}
