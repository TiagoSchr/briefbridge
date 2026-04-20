import json, time

path = r'C:\Users\User\.vscode\extensions\extensions.json'
data = json.load(open(path))

for e in data:
    if e['identifier']['id'] == 'briefbridge.briefbridge':
        e['location'] = {
            chr(36) + 'mid': 1,
            'path': '/c:/Users/User/.vscode/extensions/briefbridge.briefbridge-0.1.0',
            'scheme': 'file'
        }
        e['metadata'] = {
            'isApplicationScoped': False,
            'isMachineScoped': False,
            'isBuiltin': False,
            'installedTimestamp': int(time.time() * 1000),
            'pinned': True,
            'source': 'vsix'
        }
        print('Fixed entry:')
        print(json.dumps(e, indent=2))
        break

with open(path, 'w') as f:
    json.dump(data, f, indent='\t')
print('Saved.')
