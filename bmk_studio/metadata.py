"""Read-only format details. Values are evidence, never reconstructed generation facts."""
from __future__ import annotations
import json
import re
import xml.etree.ElementTree as ET


def object_value(value):
    for _ in range(3):
        if not isinstance(value, str): break
        try: value = json.loads(value)
        except (ValueError, TypeError): break
    return value if isinstance(value, dict) else {}


def parameter_settings(text):
    if not isinstance(text, str): return {}
    # The settings line must begin with Steps; prompt prose is not a settings record.
    match = re.search(r'(?:^|\n)Steps:\s*\d+\b[^\n]*', text)
    if not match: return {}
    line = match.group().strip()
    fields = {}; start = 0; quoted = False; escaped = False; depth = 0
    chunks = []
    for i, c in enumerate(line):
        if escaped: escaped = False; continue
        if c == '\\': escaped = True; continue
        if c == '"': quoted = not quoted
        if not quoted:
            if c in '[{(': depth += 1
            elif c in ']})': depth = max(0, depth - 1)
            elif c == ',' and depth == 0:
                chunks.append(line[start:i]); start = i + 1
    chunks.append(line[start:])
    for part in chunks:
        if ':' in part:
            key, value = part.split(':', 1)
            fields[key.strip()] = value.strip()
    return fields


def xmp_details(raw):
    result = {}; warnings = []
    for key in ('XML:com.adobe.xmp', 'xmp'):
        packet = raw.get(key)
        if not packet: continue
        if isinstance(packet, bytes): packet = packet.decode('utf-8', errors='replace')
        if not isinstance(packet, str): continue
        if len(packet) > 2_000_000 or re.search(r'<!\s*(DOCTYPE|ENTITY)', packet, re.I):
            warnings.append('XMP가 너무 크거나 DTD를 포함해 구조 분석을 생략했습니다.'); continue
        try: root = ET.fromstring(packet)
        except ET.ParseError:
            warnings.append('XMP XML 형식을 읽을 수 없습니다. 원문을 확인하세요.'); continue
        for element in root.iter():
            local = element.tag.rsplit('}', 1)[-1]
            if local in ('description', 'title', 'creator', 'DigitalImageGUID', 'DigitalSourceType', 'CreateDate'):
                values = [s.strip() for s in element.itertext() if s.strip()]
                if values: result[local] = '\n'.join(values)
            for name, value in element.attrib.items():
                local = name.rsplit('}', 1)[-1]
                if local in ('description', 'DigitalImageGUID', 'DigitalSourceType', 'CreateDate'):
                    result[local] = value
    return result, warnings


def comfy_branches(raw):
    graph = object_value(raw.get('prompt'))
    if not graph: return []
    from .graph_text import GraphText
    branches = []
    for node_id, node in graph.items():
        if not isinstance(node, dict): continue
        kind=str(node.get('class_type','')).casefold()
        if 'sampler' not in kind and 'detailer' not in kind:continue
        inputs = node.get('inputs', {})
        if not isinstance(inputs, dict):continue
        supplied={}
        if node.get('class_type')=='SamplerCustomAdvanced':
            def linked(value):
                if not isinstance(value,list) or len(value)!=2:return {}
                target=graph.get(str(value[0]),{})
                return target.get('inputs',{}) if isinstance(target,dict) else {}
            guider=linked(inputs.get('guider'))
            for key in ('noise','sampler','sigmas','guider'):
                for field,value in linked(inputs.get(key)).items():
                    if isinstance(value,(str,int,float,bool)):supplied[key+'.'+field]=value
            inputs={**inputs,**{k:v for k,v in guider.items() if k in ('positive','negative','conditioning')}}
            if 'conditioning' in inputs and 'positive' not in inputs:inputs['positive']=inputs['conditioning']
        if 'positive' not in inputs:continue
        if not supplied and not any(k in inputs for k in ('seed', 'noise_seed', 'steps', 'sampler_name')):continue
        resolver=GraphText(graph)
        positive, pw = resolver.conditioning(inputs['positive'])
        negative, nw = resolver.conditioning(inputs['negative']) if 'negative' in inputs else ([],[])
        settings = {k: v for k, v in inputs.items() if k not in ('positive','negative','model','latent_image') and not isinstance(v, (dict,list))}
        branches.append({'node': str(node_id), 'type': node.get('class_type',''), 'positive': positive,
                         'negative': negative, 'settings': {**settings,**supplied}, 'warnings': list(dict.fromkeys(pw+nw)), 'resolved_choices':resolver.trace})
    return branches


def details(raw):
    xmp, warnings = xmp_details(raw)
    comment = object_value(raw.get('Comment'))
    settings = parameter_settings(raw.get('parameters'))
    origin = 'parameters' if settings else ''
    if not settings:
        settings = parameter_settings(raw.get('UserComment'))
        if settings: origin = 'EXIF UserComment'
    if not settings and comment:
        # Retain scalar settings exactly; nested character/reference structures remain raw.
        settings = {k:v for k,v in comment.items() if k not in ('prompt','uc','negative_prompt') and isinstance(v,(str,int,float,bool))}
        if settings: origin = 'Comment'
    if not settings:
        wrapper=object_value(raw.get('forge'))
        if wrapper:
            settings={k:v for k,v in wrapper.items() if isinstance(v,(str,int,float,bool))}
            workspace=object_value(wrapper.get('image_workspace_state'))
            nested=object_value(workspace.get('settings'))
            for key,value in nested.items():
                if key not in ('prompt','negative_prompt') and isinstance(value,(str,int,float,bool)):
                    settings['workspace.'+key]=value
            origin='forge (저장된 래퍼 설정; 실제 API 적용 여부는 별도 확인)'
    branches = comfy_branches(raw)
    if len(branches) > 1: warnings.append('샘플러가 여러 개입니다. 실제 저장 이미지에 사용된 분기를 자동 확정하지 않습니다.')
    return {'settings': settings, 'settings_origin': origin, 'xmp': xmp, 'branches': branches, 'warnings': warnings}
