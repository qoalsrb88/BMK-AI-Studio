"""Local wildcard editor with a reviewable, seeded expansion."""
import os,uuid
from pathlib import Path
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPlainTextEdit,QSpinBox,QPushButton,QComboBox,QDialogButtonBox,QMessageBox)
from .prompt_tools import wildcard_path,expand_wildcards

class WildcardDialog(QDialog):
    def __init__(self,folder,positive,negative,parent=None):
        super().__init__(parent);self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.setWindowTitle('와일드카드 편집 / 확장 미리보기');self.resize(780,760);layout=QVBoxLayout(self)
        layout.addWidget(QLabel('작업 칸의 __이름__을 로컬 TXT의 한 줄로 바꿉니다. # 주석과 빈 줄은 제외합니다.'))
        self.files=QComboBox();self.files.addItem('저장된 파일 선택')
        for path in sorted(self.folder.rglob('*.txt')):self.files.addItem(path.relative_to(self.folder).with_suffix('').as_posix())
        layout.addWidget(self.files);self.name=QLineEdit();self.name.setPlaceholderText('와일드카드 이름 (예: clothes/color)');layout.addWidget(self.name)
        self.entries=QPlainTextEdit();self.entries.setPlaceholderText('선택할 내용을 한 줄씩 입력');layout.addWidget(self.entries,2)
        save=QPushButton('와일드카드 파일 저장');save.clicked.connect(self.save_file);layout.addWidget(save);self.files.currentTextChanged.connect(self.read_file)
        row=QHBoxLayout();self.target=QComboBox();self.target.addItems(['작업 프롬프트','작업 네거티브']);row.addWidget(self.target)
        self.seed=QSpinBox();self.seed.setRange(0,2147483647);row.addWidget(QLabel('시드'));row.addWidget(self.seed)
        preview=QPushButton('확장 미리보기');preview.clicked.connect(self.preview);row.addWidget(preview);layout.addLayout(row)
        self.originals=[positive,negative];self.result=None;self.used=[]
        self.output=QPlainTextEdit();self.output.setReadOnly(True);layout.addWidget(self.output,3)
        self.status=QLabel('미리보기 후 적용하면 해당 작업 칸만 변경됩니다. 원본 메타데이터는 유지됩니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Apply|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(controls)
        self.apply=controls.button(QDialogButtonBox.StandardButton.Apply);self.apply.setText('이 결과를 작업 칸에 적용');self.apply.setEnabled(False)
        self.apply.clicked.connect(self.accept);controls.rejected.connect(self.reject)
        self.target.currentIndexChanged.connect(self.invalidate);self.seed.valueChanged.connect(self.invalidate)
        self.entries.textChanged.connect(self.invalidate);self.name.textChanged.connect(self.invalidate)
    def invalidate(self,*args):self.result=None;self.apply.setEnabled(False)
    def read_file(self,name):
        if self.files.currentIndex()==0:return
        try:
            path=wildcard_path(self.folder,name)
            if path.stat().st_size>1024*1024:raise ValueError('파일은 최대 1 MB입니다.')
            self.name.setText(name);self.entries.setPlainText(path.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'와일드카드',str(exc))
    def save_file(self):
        temporary=None
        try:
            path=wildcard_path(self.folder,self.name.text().strip());text=self.entries.toPlainText()
            if len(text.encode('utf-8'))>1024*1024:raise ValueError('파일은 최대 1 MB입니다.')
            path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(uuid.uuid4().hex+'.tmp')
            with temporary.open('x',encoding='utf-8') as stream:stream.write(text)
            os.replace(temporary,path);self.invalidate();self.status.setText('저장 완료: '+str(path))
            name=path.relative_to(self.folder).with_suffix('').as_posix()
            if self.files.findText(name)<0:self.files.addItem(name)
        except (OSError,ValueError) as exc:QMessageBox.warning(self,'와일드카드',str(exc))
        finally:
            if temporary:temporary.unlink(missing_ok=True)
    def preview(self):
        self.invalidate()
        try:
            self.result,self.used=expand_wildcards(self.originals[self.target.currentIndex()],self.folder,self.seed.value())
            self.output.setPlainText(self.result);self.status.setText(f'시드 {self.seed.value()} · {len(self.used)}개 확장. 저장된 파일 내용이 사용됩니다.');self.apply.setEnabled(True)
        except (OSError,ValueError) as exc:self.output.clear();self.status.setText(str(exc))
