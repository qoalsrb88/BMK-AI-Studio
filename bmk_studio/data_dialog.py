from pathlib import Path
from PySide6.QtWidgets import QDialog,QFormLayout,QLabel,QLineEdit,QPushButton,QComboBox,QDialogButtonBox,QFileDialog

class DataDirectoryDialog(QDialog):
    def __init__(self,current,parent=None):
        super().__init__(parent);self.setWindowTitle('사용자 데이터 폴더');self.resize(680,340)
        layout=QFormLayout(self);current_label=QLineEdit(str(current));current_label.setReadOnly(True);layout.addRow('현재 폴더',current_label)
        self.target=QLineEdit();self.target.setReadOnly(True);self.target.setPlaceholderText('사용할 사용자 데이터 폴더를 선택하세요');layout.addRow('새 폴더',self.target)
        browse=QPushButton('폴더 선택…');browse.clicked.connect(lambda:self.browse(current));layout.addRow(browse)
        self.mode=QComboBox();self.mode.addItem('현재 데이터를 복사하고 사용 · 기존 폴더 보존',True);self.mode.addItem('기존 데이터 폴더 사용 / 빈 폴더에서 새로 시작',False);layout.addRow('전환 방식',self.mode)
        note=QLabel('노트·편집 보관·복구본·와일드카드·앱에서 내려받은 모델을 함께 관리합니다.\n복사 대상은 빈 폴더여야 하며, 데이터 폴더 밖의 원본 이미지와 모델은 기존 위치를 사용합니다.\n현재 작업을 저장하고 앱을 종료합니다. 다음 실행부터 새 폴더를 사용합니다.\n다른 버전의 BMK AI Studio도 모두 종료한 뒤 전환하세요.');note.setWordWrap(True);layout.addRow(note)
        self.controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        self.controls.button(QDialogButtonBox.StandardButton.Save).setText('저장 후 종료');self.controls.button(QDialogButtonBox.StandardButton.Save).setEnabled(False)
        self.target.textChanged.connect(lambda text:self.controls.button(QDialogButtonBox.StandardButton.Save).setEnabled(bool(text)))
        self.controls.accepted.connect(self.accept);self.controls.rejected.connect(self.reject);layout.addRow(self.controls)
    def browse(self,current):
        selected=QFileDialog.getExistingDirectory(self,'사용자 데이터 폴더 선택',self.target.text() or str(Path(current).parent))
        if selected:self.target.setText(selected)
