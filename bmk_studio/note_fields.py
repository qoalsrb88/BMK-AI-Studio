"""Structured BMK note fields, retaining untouched/unknown values verbatim."""
import copy,json,math
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QCheckBox,QTableWidget,QTableWidgetItem,QPushButton,QTabWidget,QDialogButtonBox,QMessageBox)

LORA=[('name','이름',''),('weight','강도',1.0),('enabled','사용',True)]
PARAM=[('label','라벨',''),('node','노드 ID',''),('widget','위젯',''),('type','타입','string'),('value','값 (JSON 스칼라)',''),('enabled','사용',True),('hint','설명','')]

class FieldsTable(QWidget):
    def __init__(self,values,columns,parent=None):
        super().__init__(parent);self.original=copy.deepcopy(values);self.columns=columns
        layout=QVBoxLayout(self);self.table=QTableWidget(0,len(columns));self.table.setHorizontalHeaderLabels([label for _,label,_ in columns]);layout.addWidget(self.table)
        self.supported=isinstance(values,list) and all(isinstance(value,dict) for value in values)
        if not self.supported:layout.addWidget(QLabel('이 필드의 기존 형식은 전체 JSON 편집에서 수정할 수 있습니다. 그대로 보존합니다.'));self.table.setEnabled(False);return
        for value in values:self.append(value)
        controls=QHBoxLayout();add=QPushButton('행 추가');remove=QPushButton('선택 행 제거');controls.addWidget(add);controls.addWidget(remove);layout.addLayout(controls)
        add.clicked.connect(lambda:self.append({key:default for key,_,default in columns}));remove.clicked.connect(self.remove_selected)
        self.table.resizeColumnsToContents()
    def append(self,value):
        row=self.table.rowCount();self.table.insertRow(row)
        header=QTableWidgetItem(str(row+1));header.setData(Qt.ItemDataRole.UserRole,copy.deepcopy(value));self.table.setVerticalHeaderItem(row,header)
        for col,(key,label,default) in enumerate(self.columns):
            original=value.get(key,default)
            if key=='enabled':
                item=QTableWidgetItem();item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if original else Qt.CheckState.Unchecked)
                baseline=bool(original)
            else:
                baseline=json.dumps(original,ensure_ascii=False) if key=='value' else str(original)
                item=QTableWidgetItem(baseline)
            item.setData(Qt.ItemDataRole.UserRole,baseline);self.table.setItem(row,col,item)
    def remove_selected(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()},reverse=True):self.table.removeRow(row)
    def values(self):
        if not self.supported:return copy.deepcopy(self.original)
        result=[]
        for row in range(self.table.rowCount()):
            value=copy.deepcopy(self.table.verticalHeaderItem(row).data(Qt.ItemDataRole.UserRole))
            for col,(key,label,default) in enumerate(self.columns):
                item=self.table.item(row,col);current=item.checkState()==Qt.CheckState.Checked if key=='enabled' else item.text()
                if current==item.data(Qt.ItemDataRole.UserRole):continue
                if key=='weight':
                    current=float(current)
                    if not math.isfinite(current):raise ValueError('LoRA 강도는 유한한 숫자여야 합니다.')
                elif key=='value':
                    current=json.loads(current)
                    if not isinstance(current,(str,int,float,bool)) or isinstance(current,float) and not math.isfinite(current):raise ValueError('파라미터 값은 문자열/숫자/불리언 JSON 스칼라여야 합니다.')
                value[key]=current
            result.append(value)
        return result

class NoteFieldsDialog(QDialog):
    def __init__(self,doc,parent=None):
        super().__init__(parent);self.original=copy.deepcopy(doc);self.result=None
        self.setWindowTitle('BMK 노트 추가 필드');self.resize(920,560);layout=QVBoxLayout(self)
        layout.addWidget(QLabel('LoRA와 파라미터는 노트 데이터로 보관합니다. 이 앱에서 모델을 적용하거나 ComfyUI 노드를 실행하지 않습니다.'))
        tabs=QTabWidget();layout.addWidget(tabs)
        self.loras=FieldsTable(doc.get('loras',[]),LORA);self.params=FieldsTable(doc.get('params',[]),PARAM)
        tabs.addTab(self.loras,'LoRA');tabs.addTab(self.params,'파라미터')
        page=QWidget();form=QFormLayout(page);tabs.addTab(page,'표시 설정')
        self.ui_original=copy.deepcopy(doc.get('ui',{}));self.ui_supported=isinstance(self.ui_original,dict)
        self.order=None;self.flags={}
        if self.ui_supported:
            order=self.ui_original.get('order',[])
            if isinstance(order,list) and all(isinstance(k,str) for k in order):
                self.order=QLineEdit(', '.join(order));form.addRow('섹션 순서 (쉼표 구분)',self.order)
                self.order_baseline=self.order.text()
            for field,label in [('collapsed','접힘'),('md','마크다운 표시')]:
                flags=self.ui_original.get(field,{})
                if not isinstance(flags,dict):continue
                widget=QWidget();row=QHBoxLayout(widget)
                for key in ('prompt','negative','loras','params','notes'):
                    check=QCheckBox(key);check.setChecked(bool(flags.get(key,False)));row.addWidget(check);self.flags[field,key]=(check,check.isChecked())
                form.addRow(label,widget)
        else:form.addRow(QLabel('기존 ui 형식은 전체 JSON 편집에서 수정할 수 있습니다. 그대로 보존합니다.'))
        layout.addWidget(QLabel('수정하지 않은 필드와 추가 키는 유지합니다. 값 칸의 문자열은 "텍스트", 불리언은 true/false로 입력합니다.'))
        controls=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);controls.accepted.connect(self.save);controls.rejected.connect(self.reject);layout.addWidget(controls)
    def document(self):
        doc=copy.deepcopy(self.original)
        for key,table in [('loras',self.loras),('params',self.params)]:
            value=table.values()
            if value!=self.original.get(key,[]):doc[key]=value
        ui=copy.deepcopy(self.ui_original)
        if self.ui_supported:
            if self.order and self.order.text()!=self.order_baseline:
                order=[key.strip() for key in self.order.text().split(',') if key.strip()]
                if len(set(order))!=len(order):raise ValueError('섹션 순서에 중복 항목이 있습니다.')
                ui['order']=order
            for (field,key),(widget,baseline) in self.flags.items():
                if widget.isChecked()!=baseline:ui.setdefault(field,{})[key]=widget.isChecked()
            if ui!=self.ui_original:doc['ui']=ui
        return doc
    def save(self):
        try:self.result=self.document()
        except (ValueError,TypeError) as exc:QMessageBox.warning(self,'필드 확인',str(exc));return
        self.accept()
