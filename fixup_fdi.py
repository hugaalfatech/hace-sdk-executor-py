# -*- coding: utf-8 -*-
"""Fix the corrupted fdi.py file."""
import ast
import sys

filepath = 'src/executor_py/io/rac/cri/fdi.py'

with open(filepath, 'r') as f:
    content = f.read()

try:
    ast.parse(content)
    print('FILE ALREADY VALID')
except SyntaxError as e:
    print(f'Syntax error at line {e.lineno}: {e.msg}')
    print('Attempting fix...')
    
    lines = content.split('\n')
    
    # Find the line with the last _FDI_CAPABILITY_MAP entry
    dict_end = None
    for i, line in enumerate(lines):
        if 'ail_summary' in line and '_FDI_CAPABILITY_MAP' not in line:
            dict_end = i
            break
    
    if dict_end is None:
        print('Could not find dict end')
        sys.exit(1)
    
    # Find the line with the first real _register_fdi_dna that has 'registry = get_dna_registry()'
    real_dna_start = None
    for i in range(dict_end, len(lines)):
        if 'registry = get_dna_registry()' in lines[i]:
            real_dna_start = i - 1  # def _register_fdi_dna line is before
            break
    
    if real_dna_start is None:
        print('Could not find real _register_fdi_dna')
        sys.exit(1)
    
    # Reconstruct lines from dict_end to real_dna_start
    new_lines = lines[:dict_end+1]
    
    # Add closing brace and proper functions
    new_lines.append('}')
    new_lines.append('')
    new_lines.append('')
    new_lines.append('def resolve_fdi_uri(rac_uri: str) -> dict:')
    new_lines.append('    """Resolve FDI URI (alias for resolve_fdi_target)."""')
    new_lines.append('    return resolve_fdi_target(rac_uri)')
    new_lines.append('')
    new_lines.append('')
    new_lines.append('def create_fdi_executor(uri: str = "") -> FdiExecutor:')
    new_lines.append('    """Create a new FDI executor with autoload transport."""')
    new_lines.append('    transport = FdiTransport(uri=uri, method=FdiMethod.FILE)')
    new_lines.append('    executor = FdiExecutor()')
    new_lines.append('    executor.transport = transport')
    new_lines.append('    return executor')
    new_lines.append('')
    new_lines.append('')
    
    # Add the real _register_fdi_dna
    new_lines.append(lines[real_dna_start])
    
    # Add the rest of the file
    new_lines.extend(lines[real_dna_start+1:])
    
    content = '\n'.join(new_lines)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    # Verify
    try:
        ast.parse(content)
        print('Fix successful - syntax OK')
    except SyntaxError as e2:
        print(f'Still syntax error: {e2}')
