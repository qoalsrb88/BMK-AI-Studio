"""Interpret a small, explicit set of serialized text/control nodes, never node code."""
CTX_KEYS=('base_ctx','model_raw','model_lora','model','clip','vae','positive','negative','pos_all','pos_artist','pos_base','pos_pre','pos_post','neg_all','wildcard','lora_triggers','lora_tags','latent','seed','steps','steps_r','cfg','shift','cfg_norm','denoise','denoise_ups','denoise_detail','sampler','scheduler','is_i2i','upscaler','upscale_by','divide_by','img_input','img_basic','img_ups','img_detail','img_merge','img_post','mask','control_net','lllite_str','lllite_end')

class Unresolved(ValueError):pass

class GraphText:
    def __init__(self,graph):self.graph=graph;self.trace=[];self.steps=0
    def node(self,link,seen):
        self.steps+=1
        if self.steps>2048 or len(seen)>96:raise Unresolved('그래프 해석 한도를 넘었습니다.')
        if not isinstance(link,list) or len(link)!=2 or not isinstance(link[1],int):raise Unresolved('유효한 노드 연결이 아닙니다.')
        key=(str(link[0]),link[1])
        if key in seen:raise Unresolved(f'{key[0]}: 순환 연결')
        node=self.graph.get(key[0])
        if not isinstance(node,dict) or not isinstance(node.get('inputs',{}),dict):raise Unresolved(f'{key[0]}: 노드 입력 없음')
        return key,node.get('class_type',''),node.get('inputs',{}),seen|{key}
    def context(self,link,field,seen):
        key,kind,inputs,seen=self.node(link,seen)
        if kind!='BMKContextAnima':raise Unresolved(f'{key[0]}: {kind} 컨텍스트 출력을 확인할 수 없습니다.')
        if inputs.get(field) is not None:return inputs[field]
        if inputs.get('base_ctx') is None:raise Unresolved(f'{key[0]}: 컨텍스트 {field} 입력이 없습니다.')
        return self.context(inputs['base_ctx'],field,seen)
    def selected(self,key,kind,inputs,seen):
        if kind in ('ComfySwitchNode','LazySwitchKJ'):
            switch=self.scalar(inputs.get('switch'),seen)
            if not isinstance(switch,bool):raise Unresolved(f'{key[0]}: 스위치의 불리언 값을 확정할 수 없습니다.')
            field='on_true' if switch else 'on_false';self.trace.append({'node':key[0],'type':kind,'selected':field})
            return inputs.get(field)
        if kind=='Any Switch (rgthree)':
            for field,value in inputs.items():
                if field.startswith('any_'):
                    if value is None:continue
                    # Unknown upstream execution may output None; do not silently skip it.
                    resolved=self.scalar(value,seen)
                    if resolved is not None:self.trace.append({'node':key[0],'type':kind,'selected':field});return value
            return None
        raise Unresolved('지원하지 않는 선택 노드')
    def scalar(self,value,seen=frozenset()):
        if not isinstance(value,list):
            if isinstance(value,(str,int,float,bool)) or value is None:return value
            raise Unresolved('미지원 정적 입력 자료형')
        key,kind,inputs,seen=self.node(value,seen)
        if kind in ('ComfySwitchNode','LazySwitchKJ','Any Switch (rgthree)'):return self.scalar(self.selected(key,kind,inputs,seen),seen)
        if kind=='BMKContextAnima':
            if not 0<key[1]<len(CTX_KEYS):raise Unresolved(f'{key[0]}: 미지원 컨텍스트 포트')
            return self.scalar(self.context([key[0],0],CTX_KEYS[key[1]],seen),seen)
        if key[1]!=0:raise Unresolved(f'{key[0]}: {kind}의 출력 포트 {key[1]}는 지원하지 않습니다.')
        if kind in ('PrimitiveString','PrimitiveStringMultiline','PrimitiveBoolean','PrimitiveInt','PrimitiveFloat','easy float'):
            return self.scalar(inputs.get('value'),seen)
        if kind=='Reroute':return self.scalar(inputs.get('value',inputs.get('input')),seen)
        if kind=='StringConcatenate':
            a=self.scalar(inputs.get('string_a'),seen);b=self.scalar(inputs.get('string_b'),seen);delimiter=self.scalar(inputs.get('delimiter',''),seen)
            if not all(isinstance(v,str) for v in (a,b,delimiter)):raise Unresolved(f'{key[0]}: 문자열 입력이 아닙니다.')
            result=delimiter.join((a,b))
            if len(result)>100000:raise Unresolved('텍스트 크기 한도를 넘었습니다.')
            return result
        raise Unresolved(f'{key[0]}: {kind} 출력은 정적으로 확인할 수 없습니다.')
    def conditioning(self,link,seen=frozenset()):
        try:key,kind,inputs,seen=self.node(link,seen)
        except Unresolved as exc:return [],[str(exc)]
        found=[];warnings=[]
        try:
            if kind in ('ComfySwitchNode','LazySwitchKJ'):
                return self.conditioning(self.selected(key,kind,inputs,seen),seen)
            if kind=='BMKContextAnima':
                if key[1] not in (6,7):raise Unresolved(f'{key[0]}: conditioning이 아닌 컨텍스트 포트')
                return self.conditioning(self.context([key[0],0],CTX_KEYS[key[1]],seen),seen)
            if kind=='ConditioningZeroOut':return [],[]
            if kind=='AnimaArtistMixerTextBlend':
                fields=('base_prompt','artist_text');warnings.append(f'{key[0]}: Artist Mixer의 {inputs.get("blend_mode","average")} conditioning을 텍스트 결합만으로 재현할 수 없습니다.')
            else:fields=('text','text_g','text_l')
            for field in fields:
                if field not in inputs:continue
                try:
                    value=self.scalar(inputs[field],seen)
                    if not isinstance(value,str):raise Unresolved(f'{key[0]}: {field}가 문자열이 아닙니다.')
                    found.append({'node':key[0],'field':field,'text':value})
                except Unresolved as exc:warnings.append(str(exc))
            for field in ('conditioning','conditioning_1','conditioning_2','positive','negative'):
                if field in inputs:
                    more,notes=self.conditioning(inputs[field],seen);found.extend(more);warnings.extend(notes)
            if any(k.startswith('conditioning') for k in inputs) and kind!='Reroute':warnings.append(f'{key[0]}: conditioning 변형은 텍스트 복사만으로 재현할 수 없습니다')
            if not found:warnings.append(f'{key[0]}: 정적 텍스트를 확인하지 못했습니다')
        except Unresolved as exc:warnings.append(str(exc))
        return found,list(dict.fromkeys(warnings))
