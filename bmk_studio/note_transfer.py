"""Explicit, source-labelled copies from images to independent prompt notes."""
import json,copy
from pathlib import Path
from PySide6.QtWidgets import QDialog,QVBoxLayout,QComboBox,QLineEdit,QLabel,QCheckBox,QPlainTextEdit,QDialogButtonBox,QScrollArea,QWidget
from .core import normalize_category


def append_transfer(body,sections,source):
    result=copy.deepcopy(body);labels=[];entries=[];counts={key:sum(1 for _,k,text in sections if k==key and text.strip()) for _,key,_ in sections}
    for label,key,text in sections:
        if not text.strip():continue
        old=result.get(key,'')
        if not isinstance(old,str):raise ValueError('기존 노트의 텍스트 형식을 확인하세요.')
        result[key]=old+('\n\n' if old else '')+(('['+label+']\n') if counts[key]>1 else '')+text;labels.append(label);entries.append({'kind':label,'field':key,'text':text})
    if not labels:raise ValueError('저장할 내용을 선택하고 입력하세요.')
    history=result.setdefault('_studio_image_transfers',[])
    if not isinstance(history,list):raise ValueError('기존 노트의 출처 기록 형식이 다릅니다. 새 노트에 저장하세요.')
    history.append({'source_image':source,'sections':entries})
    provenance='이미지에서 저장 · '+', '.join(labels)+'\n원본: '+source
    old=result.get('notes','');result['notes']=old+('\n\n' if old else '')+provenance
    return result

class NoteTransferDialog(QDialog):
    def __init__(self,owner,source,sections):
        super().__init__(owner);self.owner=owner;self.source=source;self.saved_id=None;self.setWindowTitle('노트에 저장 · 위치와 내용 확인');self.resize(700,740)
        layout=QVBoxLayout(self);label=QLabel('원본: '+source);label.setWordWrap(True);layout.addWidget(label)
        self.folder=QComboBox();self.folder.setEditable(True);self.folder.addItems(['']+sorted({r[3] for r in owner.store.note_entries() if r[3]}));self.folder.setToolTip('폴더 경로를 직접 입력하면 새 폴더에 저장합니다. 예: 캐릭터/의상');layout.addWidget(QLabel('노트 폴더 (직접 입력 가능)'));layout.addWidget(self.folder)
        self.target=QComboBox();layout.addWidget(self.target);self.title=QLineEdit(Path(source).stem+' 프롬프트');layout.addWidget(self.title)
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();fields=QVBoxLayout(content);self.sections=[]
        for label,key,text,selected in sections:
            check=QCheckBox(label);check.setChecked(selected and bool(text));editor=QPlainTextEdit(text);editor.setProperty('originalText',text);editor.setMinimumHeight(90);editor.setEnabled(check.isChecked());check.toggled.connect(editor.setEnabled);fields.addWidget(check);fields.addWidget(editor);self.sections.append((check,key,editor))
        scroll.setWidget(content);layout.addWidget(scroll,1);self.message=QLabel('선택한 내용만 복사합니다. 기존 노트는 덮어쓰지 않고 뒤에 추가합니다.');self.message.setWordWrap(True);layout.addWidget(self.message)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(self.buttons);self.buttons.accepted.connect(self.commit);self.buttons.rejected.connect(self.reject)
        self.folder.currentTextChanged.connect(self.refresh_targets);self.target.currentIndexChanged.connect(lambda:self.title.setEnabled(self.target.currentData() is None));self.refresh_targets()
    def refresh_targets(self):
        self.target.clear();self.target.addItem('새 노트 만들기',None)
        for nid,title,body,category,archived in self.owner.store.note_entries():
            if not archived and category==normalize_category(self.folder.currentText()):self.target.addItem('기존 노트에 추가: '+title,nid)
    def commit(self):
        try:
            nid=self.target.currentData();record=self.owner.store.note(nid) if nid else None
            if nid and (not record or record[4]):raise ValueError('선택한 노트를 다시 확인하세요.')
            body=json.loads(record[2]) if record else {'schema':1,'prompt':'','negative':'','notes':''}
            sections=[(check.text()+(' · 저장본 편집' if editor.toPlainText()!=editor.property('originalText') else ''),key,editor.toPlainText()) for check,key,editor in self.sections if check.isChecked()]
            body=append_transfer(body,sections,self.source);title=record[1] if record else self.title.text().strip()
            if not title:raise ValueError('새 노트 제목을 입력하세요.')
            self.saved_id=self.owner.store.save_note(title,body,nid,record[3] if record else normalize_category(self.folder.currentText()));self.accept()
        except Exception as exc:self.message.setText(str(exc))
