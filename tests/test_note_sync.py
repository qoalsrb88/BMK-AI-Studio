import json,os,tempfile,unittest,zipfile
from pathlib import Path
from bmk_studio.core import Store
from bmk_studio.note_sync import (NoteFolderSync,NoteSyncError,BASE_KEY,MASS_MISSING,encode,note_path,path_category,safe_name,title_for,
                                  forget_file_base,backup_folder,plan_question,report_summary)

COMFY={'prompt':'1girl','negative':'lowres','loras':[{'name':'style','weight':.8,'enabled':True}],'notes':'memo'}

def node_write(path,doc):
    """What the ComfyUI node does on save: indent 1, LF, plus a .txt mirror."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf-8',newline='') as f:json.dump(doc,f,ensure_ascii=False,indent=1)
    path.with_suffix('.txt').write_text('[Prompt]\n'+doc.get('prompt',''),encoding='utf-8')
    return path

class NoteSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.folder=self.root/'bmk_notes';self.folder.mkdir()
        self.store=Store(self.root/'data');self.cache={}
        (self.folder/'.bmk_meta.json').write_text('{"categories":[]}',encoding='utf-8')
        (self.folder/'.bmk_param_presets.json').write_text('{"presets":[]}',encoding='utf-8')
    def tearDown(self):self.store.db.close();self.temp.cleanup()
    def engine(self):return NoteFolderSync(self.store,self.folder,self.cache)
    def sync(self):
        engine=self.engine();plan=engine.plan();return plan,engine.apply(plan)
    def body(self,nid):return json.loads(self.store.note(nid)[2])
    def file(self,rel):return json.loads((self.folder/rel).read_text(encoding='utf-8'))
    def entries(self):return {(r[3],r[1]):r for r in self.store.note_entries()}
    def assert_quiet(self):
        plan=self.engine().plan()
        self.assertEqual([a['op'] for a in plan['actions']],[]);self.assertEqual(plan['conflicts'],[])

    def connect(self):
        node_write(self.folder/'캐릭터'/'hero.json',COMFY);node_write(self.folder/'캐릭터'/'의상'/'coat.json',{**COMFY,'prompt':'coat'})
        node_write(self.folder/'.trash'/'20260101_000000_old.json',COMFY);(self.folder/'root.json').write_text(json.dumps(COMFY),encoding='utf-8')
        (self.folder/'캐릭터'/'workflow.json').write_text('{"nodes":[],"links":[]}',encoding='utf-8')
        same=self.store.save_note('hero',{'schema':1,'source':None,**COMFY},category='캐릭터')
        new=self.store.save_note('새 노트',{'schema':1,'prompt':'mine','negative':'','notes':'','source':'C:/img.png','future':{'kept':[1]}},category='MOSS')
        loose=self.store.save_note('loose',{'prompt':'p','negative':'','notes':''})
        clash=self.store.save_note('coat',{'prompt':'app coat','negative':'','notes':''},category='캐릭터/의상')
        archived=self.store.save_note('gone',{'prompt':'x','negative':'','notes':''},category='캐릭터');self.store.archive_note(archived)
        return same,new,loose,clash

    def test_first_connect_links_writes_and_reports_conflicts(self):
        same,new,loose,clash=self.connect()
        engine=self.engine();self.assertTrue(engine.fresh());plan=engine.plan()
        self.assertEqual(plan['counts'],{'link':1,'write':2});self.assertEqual([c['kind'] for c in plan['conflicts']],['occupied'])
        self.assertEqual(plan['conflicts'][0]['note_id'],clash);self.assertEqual(plan['ignored'],{'ComfyUI 워크플로':1})
        self.assertIn('MOSS (1)',plan_question(plan));self.assertIn('미분류 (1)',plan_question(plan))
        report=engine.apply(plan);self.assertEqual((report['written'],report['linked'],report['failed']),(2,1,[]))
        written=self.file('MOSS/새 노트.json');self.assertEqual(written,{'prompt':'mine','negative':'','notes':'','future':{'kept':[1]}})
        raw=(self.folder/'MOSS'/'새 노트.json').read_bytes();self.assertEqual(raw,encode(written));self.assertNotIn(b'\r\n',raw);self.assertFalse(raw.endswith(b'\n'))
        self.assertEqual(self.file('미분류/loose.json')['prompt'],'p');self.assertFalse((self.folder/'캐릭터'/'gone.json').exists())
        self.assertEqual(self.file('캐릭터/의상/coat.json')['prompt'],'coat')  # the clash is not overwritten
        self.assertEqual((self.folder/'.bmk_meta.json').read_text(encoding='utf-8'),'{"categories":[]}')
        self.assertEqual(len(self.store.note_entries()),4);self.assertFalse(self.engine().fresh())
        self.assertFalse(any(Path(p).name.startswith('.') and p.endswith('.tmp') for p in os.listdir(self.folder/'MOSS')))
        plan=self.engine().plan();self.assertEqual(plan['actions'],[]);self.assertEqual(len(plan['conflicts']),1)
        self.assertIn('충돌 1개',report_summary(report))

    def test_resolve_occupied_keep_app_and_keep_file(self):
        same,new,loose,clash=self.connect();self.sync()
        self.engine().resolve(clash,'캐릭터/의상/coat.json','app')
        self.assertEqual(self.file('캐릭터/의상/coat.json')['prompt'],'app coat')
        trash=sorted(p.name for p in (self.folder/'.trash').iterdir());self.assertTrue(any(n.endswith('_coat.json') for n in trash));self.assertTrue(any(n.endswith('_coat.txt') for n in trash))
        self.assert_quiet()
        # keep file: ComfyUI and the app both change; the app takes the file, its own text stays in history.
        node_write(self.folder/'캐릭터'/'hero.json',{**COMFY,'prompt':'comfy edit'})
        self.store.save_note('hero',{'schema':1,'source':None,**COMFY,'prompt':'app edit'},same,'캐릭터')
        plan,report=self.sync();self.assertEqual([c['kind'] for c in report['conflicts']],['both']);self.assertEqual(self.file('캐릭터/hero.json')['prompt'],'comfy edit')
        self.engine().resolve(same,'캐릭터/hero.json','file')
        body=self.body(same);self.assertEqual(body['prompt'],'comfy edit');self.assertEqual((body['schema'],body['source']),(1,None))
        self.assertIn('app edit',[json.loads(r[2])['prompt'] for r in self.store.revisions(same)])
        self.assert_quiet()

    def test_app_edits_rename_move_archive_and_restore(self):
        same,new,loose,clash=self.connect();self.sync();self.engine().resolve(clash,'캐릭터/의상/coat.json','file')
        self.store.save_note('hero',{'schema':1,'source':None,**COMFY,'prompt':'edited','extra':True},same,'캐릭터')
        plan,report=self.sync();self.assertEqual(report['written'],1)
        self.assertEqual(self.file('캐릭터/hero.json'),{**COMFY,'prompt':'edited','extra':True});self.assert_quiet()
        # ComfyUI rewrites its txt mirror itself; a moved note takes the mirror along and empty app folders go away.
        (self.folder/'MOSS'/'새 노트.txt').write_text('mirror',encoding='utf-8')
        self.store.save_note('renamed',self.body(new),new,'MOSS/sub');self.sync()
        self.assertTrue((self.folder/'MOSS'/'sub'/'renamed.json').exists());self.assertEqual((self.folder/'MOSS'/'sub'/'renamed.txt').read_text(encoding='utf-8'),'mirror')
        self.assertFalse((self.folder/'MOSS'/'새 노트.json').exists());self.assert_quiet()
        self.store.save_note('renamed',self.body(new),new,'다른곳');self.sync()
        self.assertTrue((self.folder/'다른곳'/'renamed.json').exists());self.assertFalse((self.folder/'MOSS').exists())  # app-created, now empty
        (self.folder/'캐릭터'/'keep.json').write_text(json.dumps(COMFY),encoding='utf-8');self.sync()
        self.store.save_note('hero',self.body(same),same,'영웅');self.sync()
        self.assertTrue((self.folder/'캐릭터').is_dir())  # a ComfyUI folder is never removed
        self.store.save_note('Hero',self.body(same),same,'영웅');self.sync()
        self.assertIn('Hero.json',os.listdir(self.folder/'영웅'))  # case-only rename
        self.store.archive_note(same);plan,report=self.sync();self.assertEqual(report['trashed'],1);self.assertFalse((self.folder/'영웅'/'Hero.json').exists())
        self.store.archive_note(same,False);self.sync();self.assertEqual(self.file('영웅/Hero.json')['prompt'],'edited');self.assert_quiet()

    def test_comfy_edits_renames_moves_and_deletes(self):
        same,new,loose,clash=self.connect();self.sync();self.engine().resolve(clash,'캐릭터/의상/coat.json','file')
        self.assertEqual(self.body(clash)['prompt'],'coat');self.assert_quiet()
        node_write(self.folder/'캐릭터'/'hero.json',{**COMFY,'prompt':'comfy','params':[{'value':1}]})
        plan,report=self.sync();self.assertEqual(report['updated'],[same])
        body=self.body(same);self.assertEqual((body['prompt'],body['params'],body['schema']),('comfy',[{'value':1}],1));self.assert_quiet()
        (self.folder/'캐릭터'/'renamed hero.json').parent.mkdir(exist_ok=True)
        os.rename(self.folder/'캐릭터'/'hero.json',self.folder/'캐릭터'/'renamed hero.json')
        plan,report=self.sync();self.assertEqual(report['imported'],[]);self.assertEqual(self.store.note(same)[1],'renamed hero')
        (self.folder/'새 분류').mkdir();os.rename(self.folder/'캐릭터'/'renamed hero.json',self.folder/'새 분류'/'renamed hero.json')
        self.sync();self.assertEqual(self.store.note(same)[3],'새 분류');self.assert_quiet()
        node_write(self.folder/'미분류'/'from comfy.json',{**COMFY,'prompt':'new'});node_write(self.folder/'깊은'/'곳'/'n.json',COMFY)
        plan,report=self.sync();self.assertEqual(len(report['imported']),2)
        self.assertEqual(self.entries()[('','from comfy')][1],'from comfy');self.assertIn(('깊은/곳','n'),self.entries())
        os.rename(self.folder/'새 분류'/'renamed hero.json',self.folder/'.trash'/'x_renamed hero.json')
        plan,report=self.sync();self.assertEqual(report['archived'],[same]);self.assertTrue(self.store.note(same)[4]);self.assert_quiet()

    def test_mass_missing_blocks_and_both_changed_writes_nothing(self):
        for i in range(MASS_MISSING):node_write(self.folder/'많은'/f'n{i}.json',{**COMFY,'prompt':f'p{i}'})
        self.sync();self.assertEqual(len(self.store.note_entries()),MASS_MISSING)
        for i in range(MASS_MISSING):(self.folder/'많은'/f'n{i}.json').unlink()
        plan=self.engine().plan();self.assertEqual(plan['blocked'],'missing');self.assertEqual(plan['archives'],MASS_MISSING)
        (self.folder/'gone').mkdir();self.assertRaises(NoteSyncError,NoteFolderSync(self.store,self.root/'nowhere').plan)

    def test_file_changed_after_planning_is_not_overwritten(self):
        nid=self.store.save_note('a',{'prompt':'app','negative':'','notes':''},category='c');self.sync()
        self.store.save_note('a',{'prompt':'app 2','negative':'','notes':''},nid,'c')
        engine=self.engine();plan=engine.plan();node_write(self.folder/'c'/'a.json',{**COMFY,'prompt':'comfy wins race'})
        report=engine.apply(plan);self.assertEqual((report['written'],report['skipped']),(0,1))
        self.assertEqual(self.file('c/a.json')['prompt'],'comfy wins race')
        plan=self.engine().plan();self.assertEqual([c['kind'] for c in plan['conflicts']],['both'])
        # The app note changed after planning: the file content is not taken over it.
        self.store.save_note('b',{'prompt':'b','negative':'','notes':''},category='c');self.sync()
        nid_b=self.entries()[('c','b')][0];node_write(self.folder/'c'/'b.json',{**COMFY,'prompt':'comfy b'})
        engine=self.engine();plan=engine.plan();self.store.save_note('b',{'prompt':'typed','negative':'','notes':''},nid_b,'c')
        report=engine.apply(plan);self.assertEqual(report['updated'],[]);self.assertEqual(self.body(nid_b)['prompt'],'typed')

    def test_duplicates_long_paths_and_editor_race(self):
        first=self.store.save_note('sa_me',{'prompt':'1','negative':'','notes':''},category='c')
        second=self.store.save_note('sa:me',{'prompt':'2','negative':'','notes':''},category='c')
        self.store.save_note('x'*250,{'prompt':'long','negative':'','notes':''},category='c')
        plan,report=self.sync();self.assertEqual(report['written'],1);self.assertEqual([c['kind'] for c in report['conflicts']],['duplicate'])
        self.assertTrue(any('240' in p['reason'] for p in report['problems']))
        self.assertEqual(self.file('c/sa_me.json')['prompt'],'2')  # the most recently saved note takes the name
        linked=self.store.db.execute('SELECT note_id FROM note_sync').fetchone()[0]
        node_write(self.folder/'c'/(Path(note_path(self.store.note(linked)[1],'c')).name),{**COMFY,'prompt':'comfy'})
        self.sync();forget_file_base(self.store,linked)
        self.assertEqual([a['op'] for a in self.engine().plan()['actions']],['link'])  # unchanged editor: nothing to ask
        forget_file_base(self.store,linked);self.store.save_note(self.store.note(linked)[1],{'prompt':'typed','negative':'','notes':''},linked,'c')
        self.assertEqual([c['kind'] for c in self.engine().plan()['conflicts'] if c['note_id']==linked],['both'])

    def test_names_backup_and_other_folder(self):
        self.assertEqual(safe_name(' .a:b?. '),'a_b_');self.assertEqual(note_path('',''),'미분류/제목 없는 노트.json')
        self.assertEqual(note_path('t','a/..b'),'a/b/t.json');self.assertEqual(path_category('미분류/x.json'),'');self.assertEqual(path_category('미분류/y/x.json'),'미분류/y')
        self.assertEqual(title_for('c/a_b.json','a:b'),'a:b');self.assertEqual(title_for('c/a_b.json','zz'),'a_b')
        node_write(self.folder/'c'/'n.json',COMFY);backup=backup_folder(self.folder,self.root/'backups')
        with zipfile.ZipFile(backup['path']) as archive:names=set(archive.namelist())
        self.assertEqual(names,{'.bmk_meta.json','.bmk_param_presets.json','c/n.json','c/n.txt'})
        self.sync();self.assertEqual(len(self.store.note_entries()),1)
        other=self.root/'other';other.mkdir();engine=NoteFolderSync(self.store,other)
        self.assertTrue(engine.fresh());plan=engine.plan();self.assertEqual(plan['counts'],{'write':1});engine.apply(plan)
        self.assertTrue((other/'c'/'n.json').exists());self.assertEqual(self.store.state(BASE_KEY)['folder'],os.path.normcase(os.path.abspath(other)))

if __name__=='__main__':unittest.main()
