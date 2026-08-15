# -*- coding: utf-8 -*-
import re

filepath = 'src/executor_py/io/rac/cri/fdi.py'
with open(filepath, 'r') as f:
    content = f.read()

pattern = r'(    "fdi\.str\.ail_summary".*?registry = get_dna_registry\(\))'
match = re.search(pattern, content, re.DOTALL)
if match:
    new = '    "fdi.str.ail_summary": ("text_editor.addon.ail_machine.bridge", "ail_summary"),
}\n\n\ndef resolve_fdi_uri(rac_uri: str) -> dict:\n    return resolve_fdi_target(rac_uri)\n\n\ndef create_fdi_executor(uri: str = "") -> FdiExecutor:\n    """Create a new FDI executor with autoload transport."""\n    transport = FdiTransport(uri=uri, method=FdiMethod.FILE)\n    executor = FdiExecutor()\n    executor.transport = transport\n    return executor\n\n\ndef _register_fdi_dna():\n    registry = get_dna_registry()'
    content = content[:match.start()] + new + content[match.end():]
    with open(filepath, 'w') as f:
        f.write(content)
    print('FIXED successfully')
else:
    print('NOT FOUND')
    lines = content.split('\n')
    for i, l in enumerate(lines[392:420], start=393):
        print(i, repr(l))