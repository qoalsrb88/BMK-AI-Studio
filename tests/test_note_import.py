import json,tempfile,unittest
from pathlib import Path
from bmk_studio.core import (Store,NOTE_CONFLICT,NOTE_SAME,note_json_files,note_skip_reason,note_import_exclusion,
                             note_import_question,note_import_summary)

COMFY_NOTE={'prompt':'1girl, solo','negative':'lowres','notes':'memo','loras':[{'name':'style','weight':.8,'enabled':True}],'ui':{'order':['prompt']}}

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return path

class NoteImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folder=self.root/'bmk_notes'
        self.store=Store(self.root/'data')
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def import_folder(self):return self.store.import_note_files(note_json_files(self.folder),self.folder)
    def kinds(self,report):return sorted((Path(item['path']).name,item['kind']) for item in report['skipped'])

    def test_folder_partial_failure_unknown_fields(self):
        valid=write(self.folder/'character'/'one.json',{'prompt':'bird','schema':7,'params':{'seed':9}})
        invalid=write(self.folder/'bad.json','{broken');damaged=write(self.folder/'wrong.json',{'prompt':'x','negative':42})
        report=self.store.import_note_files([invalid,valid,damaged],self.folder)
        self.assertEqual(len(report['imported']),1);self.assertEqual(len(report['failed']),2);self.assertEqual(report['skipped'],[])
        record=self.store.note(report['imported'][0]['id']);self.assertEqual(record[3],'character')
        self.assertEqual(json.loads(record[2])['params'],{'seed':9});self.assertEqual(json.loads(record[2])['schema'],7)

    def test_trash_settings_and_non_note_json_are_skipped(self):
        write(self.folder/'캐릭터'/'hero.json',COMFY_NOTE)
        write(self.folder/'export.json',{'schema':1,'prompt':'p','negative':'','notes':'','_studio_category':'내보냄/폴더'})
        write(self.folder/'.bmk_meta.json',{'categories':['캐릭터']});write(self.folder/'.bmk_param_presets.json',{'presets':[]})
        write(self.folder/'.trash'/'deleted.json',COMFY_NOTE);write(self.folder/'캐릭터'/'.Trash'/'old.json',COMFY_NOTE)
        write(self.folder/'workflow.json',{'last_node_id':3,'nodes':[{'id':3,'type':'KSampler'}],'links':[],'version':.4})
        write(self.folder/'api.json',{'3':{'class_type':'KSampler','inputs':{'seed':1}}})
        write(self.folder/'image_meta.json',{'prompt':{'3':{'class_type':'KSampler'}},'workflow':{'nodes':[]}})
        write(self.folder/'bot_settings.json',{'prompt':'You are a helpful bot','model':'x','temperature':.7})
        write(self.folder/'cache.json',[1,2,3])
        report=self.import_folder()
        self.assertEqual(sorted(self.store.note(item['id'])[1] for item in report['imported']),['export','hero'])
        self.assertEqual({r[1]:r[3] for r in self.store.note_entries()},{'hero':'캐릭터','export':'내보냄/폴더'})
        self.assertEqual(self.kinds(report),[('.bmk_meta.json','excluded'),('.bmk_param_presets.json','excluded'),('api.json','not_note'),
            ('bot_settings.json','not_note'),('cache.json','not_note'),('deleted.json','excluded'),('image_meta.json','not_note'),
            ('old.json','excluded'),('workflow.json','not_note')])
        self.assertEqual(report['failed'],[]);self.assertEqual(report['scanned'],11)

    def test_note_shape_rules(self):
        accepted=[COMFY_NOTE,{'prompt':'','negative':'','notes':''},{'prompt':'only','loras':[]},{'notes':'memo','params':[]},
                  {'schema':1,'prompt':'p','negative':'n','notes':'','source':None,'future':{'kept':True}}]
        for doc in accepted:self.assertIsNone(note_skip_reason(doc),doc)
        rejected={'JSON 객체가 아님':[[],'text',3],'ComfyUI 워크플로':[{'nodes':[],'links':[],'prompt':'x','notes':''}],
                  'ComfyUI API 프롬프트':[{'1':{'class_type':'CLIPTextEncode','inputs':{'text':'x'}},'prompt':'a','negative':'b'}],
                  'BMK 노트 필드(prompt·negative·notes) 없음':[{},{'theme':'dark'},{'prompt':{'3':{}},'workflow':{}},{'prompt':42}],
                  'BMK 노트 형식이 아님 (노트 필드 하나만 있음)':[{'prompt':'x'},{'notes':'todo','title':'t','schema':1}]}
        for reason,docs in rejected.items():
            for doc in docs:self.assertEqual(note_skip_reason(doc),reason,doc)
        self.assertIsNotNone(note_import_exclusion(self.root/'elsewhere'/'.BMK_meta.json'))
        self.assertIsNone(note_import_exclusion(self.folder/'.trash'/'chosen.json'))  # explicit file choice
        self.assertIsNone(note_import_exclusion(self.folder/'.trash'/'a.json',self.folder/'.trash'))  # the trash folder itself was chosen

    def test_reimport_skips_same_and_reports_changed_without_overwriting(self):
        hero=write(self.folder/'캐릭터'/'hero.json',COMFY_NOTE);write(self.folder/'scene.json',{'prompt':'beach','negative':'','notes':''})
        first=self.import_folder();self.assertEqual(len(first['imported']),2)
        again=self.import_folder();self.assertEqual(again['imported'],[])
        self.assertEqual(self.kinds(again),[('hero.json','same'),('scene.json','same')])
        self.assertEqual({item['reason'] for item in again['skipped']},{NOTE_SAME})
        hero_id=next(item['id'] for item in first['imported'] if item['path']==str(hero))
        write(hero,{**COMFY_NOTE,'prompt':'1girl, edited in ComfyUI'});write(self.folder/'new.json',{'prompt':'new','negative':'','notes':''})
        changed=self.import_folder()
        self.assertEqual([Path(item['path']).name for item in changed['imported']],['new.json'])
        self.assertEqual(self.kinds(changed),[('hero.json','conflict'),('scene.json','same')])
        conflict=next(item for item in changed['skipped'] if item['kind']=='conflict')
        self.assertEqual((conflict['title'],conflict['category'],conflict['reason']),('hero','캐릭터',NOTE_CONFLICT))
        self.assertEqual(json.loads(self.store.note(hero_id)[2]),COMFY_NOTE);self.assertEqual(len(self.store.revisions(hero_id)),1)
        self.assertEqual(len(self.store.note_entries()),3)

    def test_existing_note_matching_rules(self):
        write(self.folder/'archived.json',COMFY_NOTE);write(self.folder/'viewed.json',COMFY_NOTE);write(self.folder/'other.json',COMFY_NOTE)
        archived=self.store.save_note('archived',COMFY_NOTE);self.store.archive_note(archived)
        # 0.9.14 and earlier re-saved viewed notes with schema/source; the file's own fields still match.
        self.store.save_note('viewed',{**COMFY_NOTE,'schema':1,'source':'C:/images/opened.png'})
        self.store.save_note('other',COMFY_NOTE,category='다른 폴더')
        report=self.import_folder()
        self.assertEqual([Path(item['path']).name for item in report['imported']],['other.json'])
        self.assertEqual(self.kinds(report),[('archived.json','same'),('viewed.json','same')])
        write(self.folder/'schema.json',{**COMFY_NOTE,'schema':2});self.store.save_note('schema',{**COMFY_NOTE,'schema':1})
        self.assertEqual(self.kinds(self.store.import_note_files([self.folder/'schema.json'],self.folder)),[('schema.json','conflict')])

    def test_same_category_and_title_within_one_import_creates_one_note(self):
        write(self.folder/'a'/'dup.json',{**COMFY_NOTE,'_studio_category':'공통'});write(self.folder/'b'/'dup.json',{**COMFY_NOTE,'_studio_category':'공통','prompt':'other'})
        write(self.folder/'c'/'dup.json',{**COMFY_NOTE,'_studio_category':'공통'})
        report=self.import_folder()
        self.assertEqual(len(report['imported']),1);self.assertEqual(sorted(item['kind'] for item in report['skipped']),['conflict','same'])
        self.assertEqual(len(self.store.note_entries()),1)

    def test_apply_rechecks_notes_created_after_planning(self):
        write(self.folder/'late.json',COMFY_NOTE)
        plan=self.store.plan_note_import(note_json_files(self.folder),self.folder);self.assertEqual(len(plan['import']),1)
        self.assertEqual(len(self.store.note_entries()),0)  # planning never writes
        nid=self.store.save_note('late',{'prompt':'typed meanwhile','negative':'','notes':''})
        report=self.store.apply_note_import(plan)
        self.assertEqual(report['imported'],[]);self.assertEqual(self.kinds(report),[('late.json','conflict')])
        self.assertEqual(json.loads(self.store.note(nid)[2])['prompt'],'typed meanwhile')
        # Two imports planned before either ran (double click): the second creates nothing.
        write(self.folder/'twice.json',COMFY_NOTE)
        first,second=(self.store.plan_note_import(note_json_files(self.folder),self.folder) for _ in range(2))
        self.assertEqual(len(self.store.apply_note_import(first)['imported']),1)
        self.assertEqual(self.store.apply_note_import(second)['imported'],[]);self.assertEqual(len(self.store.note_entries()),2)

    def test_question_and_summary_texts(self):
        for i in range(3):write(self.folder/f'캐릭터/{i}.json',COMFY_NOTE)
        write(self.folder/'root.json',COMFY_NOTE);write(self.folder/'workflow.json',{'nodes':[],'links':[]});write(self.folder/'bad.json','{')
        plan=self.store.plan_note_import(note_json_files(self.folder),self.folder);question=note_import_question(plan)
        for text in ('폴더: '+str(self.folder),'JSON 파일 6개를 확인했습니다.','새로 가져올 노트: 4개','건너뜀: 1개 / 실패: 1개','캐릭터 3개','(최상위) 1개'):
            self.assertIn(text,question)
        report=self.store.apply_note_import(plan);write(self.folder/'root.json',{**COMFY_NOTE,'notes':'changed'})
        report=self.import_folder();status,message,details=note_import_summary(report,limit=2)
        self.assertEqual(status,'노트 가져오기: 성공 0개 / 건너뜀 5개 / 실패 1개');self.assertIn(status,message)
        self.assertIn('· 건너뜀 3개: '+NOTE_SAME,message);self.assertIn('기존 노트와 이력을 그대로',message)
        self.assertIn('\nroot.json → (최상위) / root',details);self.assertIn('[실패] 1개\nbad.json: ',details)
        self.assertIn('… 외 1개',details);self.assertLess(details.index('[실패]'),details.index('[내용이 달라 건너뜀]'))
        self.assertLess(details.index(NOTE_SAME),details.index('ComfyUI 워크플로'))  # sections follow the summary order (most first)
        self.assertEqual(note_import_summary({'imported':[{}],'skipped':[],'failed':[]})[2],'')

    def test_state_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(temp);store.state('documents',{'ids':['one'],'active':'one'});store.db.close()
            store=Store(temp);self.assertEqual(store.state('documents')['ids'],['one'])
            with store.db:store.db.execute('UPDATE app_state SET value=?',('{broken',))
            self.assertIsNone(store.state('documents'));store.db.close()

if __name__=='__main__':unittest.main()
