"""Read-only compatibility audit of user-selected original exports; never prints prompts."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bmk_studio.core import inspect_image,fingerprint,EXTENSIONS
from bmk_studio.metadata import object_value

counts={'files':0,'embedded_text':0,'graph_only':0,'no_prompt':0,'source_unchanged':0}
for path in sorted(Path(sys.argv[1]).iterdir()):
    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:continue
    before=fingerprint(path);info=inspect_image(path);raw=info['raw'];counts['files']+=1
    if info['positive']:counts['embedded_text']+=1
    elif any(b['positive'] or b['negative'] for b in info['branches']):counts['graph_only']+=1
    else:counts['no_prompt']+=1
    if 'parameters' in raw:
        expected=raw['parameters'].split('\nNegative prompt:')[0].split('\nSteps:')[0].strip()
        assert info['positive']==expected,'parameters text changed'
    comment=object_value(raw.get('Comment'))
    if 'v4_prompt' in comment:
        assert info['positive']==comment['v4_prompt']['caption']['base_caption'].strip()
    forge=object_value(raw.get('forge'));workspace=object_value(forge.get('image_workspace_state'))
    settings=object_value(workspace.get('settings'))
    if settings.get('prompt'):assert info['positive']==settings['prompt'].strip()
    elif forge:assert not info['positive'],'Invented wrapper prompt'
    if raw.get('Description') and not comment:assert info['positive']==raw['Description'].strip()
    assert before==fingerprint(path),'Source file modified'
    counts['source_unchanged']+=1
assert counts['files']>0,'No samples found'
print('PASS: original export text fidelity, explicit graph candidates, missing prompt separation, source hashes; '+json.dumps(counts))
