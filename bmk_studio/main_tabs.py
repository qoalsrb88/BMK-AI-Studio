"""Top-level task tabs, preserving image and note editing contexts."""
from PySide6.QtWidgets import QWidget,QVBoxLayout,QSplitter,QTabBar,QDialog,QLabel,QPlainTextDocumentLayout,QScrollArea
from PySide6.QtGui import QTextDocument,QTextCursor
from .workspace import action,line

class MainTabsMixin:
    def build_main_tabs(self,outer):
        self.main_switching=False;self.editor_contexts={};self.last_note_index=1;self.last_image_mode=0
        self.main_tabs=QTabBar();self.main_tabs.setExpanding(False)
        for title in ('파일 탐색','이미지 라이브러리','노트'):self.main_tabs.addTab(title)
        self.main_tabs.setCurrentIndex(1);outer.insertWidget(0,self.main_tabs)
        self.notes_page=QSplitter();self.notes_page.addWidget(self.note_browser);self.note_editor_host=QWidget();self.note_editor_layout=QVBoxLayout(self.note_editor_host);self.note_editor_scroll=QScrollArea();self.note_editor_scroll.setWidgetResizable(True);self.note_editor_scroll.setWidget(self.note_editor_host);self.notes_page.addWidget(self.note_editor_scroll);self.notes_page.setSizes([300,1000]);self.notes_page.hide();outer.addWidget(self.notes_page,1)
        self.open_saved_note=action('저장한 노트 열기',self.open_transferred_note);self.open_saved_note.hide();outer.addWidget(self.open_saved_note)
        self.image_view_modes=QTabBar();self.image_view_modes.addTab('갤러리');self.image_view_modes.addTab('큰 미리보기');self.image_view_modes.currentChanged.connect(lambda i:self.workspace_mode.setCurrentIndex(i));self.image_work_layout.insertWidget(0,QLabel('이미지에 연결된 작업 프롬프트'))
        self.main_splitter.widget(1).layout().insertWidget(0,self.image_view_modes)
        self.note_send_button=action('현재 이미지의 작업 프롬프트로 보내기…',self.note_to_image);self.note_editor_layout.addWidget(self.note_send_button)
        self.main_tabs.currentChanged.connect(self.change_main_tab);self.workspace_mode.hide();self.apply_main_visibility()
    def hold_editor(self):
        key=('note',self.note_id or self.document_index) if self.note_mode else ('image',str(self.path))
        values=[]
        for editor in (self.draft,self.draft_negative,self.memo):
            doc=editor.document();doc.setParent(self);values.append((doc,editor.textCursor().position(),editor.verticalScrollBar().value()))
            replacement=QTextDocument(editor);replacement.setDocumentLayout(QPlainTextDocumentLayout(replacement));editor.blockSignals(True);editor.setDocument(replacement);editor.blockSignals(False)
        self.editor_contexts[key]=values
    def restore_editor_context(self):
        key=('note',self.note_id or self.document_index) if self.note_mode else ('image',str(self.path));values=self.editor_contexts.pop(key,None)
        if not values:return
        for editor,(doc,cursor,scroll) in zip((self.draft,self.draft_negative,self.memo),values):
            if doc.toPlainText()==editor.toPlainText() or (key[0]=='image' and not self.path):
                editor.blockSignals(True);editor.setDocument(doc);c=editor.textCursor();c.setPosition(min(cursor,len(editor.toPlainText())));editor.setTextCursor(c);editor.verticalScrollBar().setValue(scroll);editor.blockSignals(False)
            else:doc.deleteLater()
    def change_main_tab(self,index):
        if self.main_switching:return
        self.main_switching=True
        try:
            if index==2 and not self.note_mode:
                self.save_draft();self.hold_editor()
                if self.note_tabs.count()>1:self.activate_document(min(self.last_note_index,self.note_tabs.count()-1),save=False)
                else:self.loading=True;self.new_note()
                self.restore_editor_context()
            elif index!=2 and self.note_mode:
                self.save_draft();self.last_note_index=self.document_index;self.hold_editor();self.activate_document(0,save=False);self.restore_editor_context()
            if index==0:self.workspace_mode.setCurrentIndex(2)
            elif index==1:self.workspace_mode.setCurrentIndex(self.last_image_mode)
            self.apply_main_visibility()
        finally:self.main_switching=False
    def apply_main_visibility(self):
        if not hasattr(self,'main_tabs'):return
        index=self.main_tabs.currentIndex();notes=index==2
        self.main_splitter.setVisible(index==1);self.disk_browser.setVisible(index==0);self.disk_browser.set_active(index==0);self.notes_page.setVisible(notes)
        (self.note_editor_layout if notes else self.image_work_layout).addWidget(self.prompt_editor);self.prompt_editor.show()
        for widget in self.note_only_controls:widget.setVisible(notes)
        self.work_prompt_header.layout().itemAt(0).widget().setText('노트 프롬프트' if notes else '작업 프롬프트');self.work_negative_header.layout().itemAt(0).widget().setText('노트 네거티브' if notes else '작업 네거티브');self.image_note_save.setVisible(not notes);self.note_tabs.setTabVisible(0,False)
    def workspace_to_main(self,mode):
        if not hasattr(self,'main_tabs'):return
        if mode!='disk':self.last_image_mode=0 if mode=='browse' else 1;self.image_view_modes.blockSignals(True);self.image_view_modes.setCurrentIndex(self.last_image_mode);self.image_view_modes.blockSignals(False)
        if not self.main_switching:self.main_tabs.setCurrentIndex(0 if mode=='disk' else 1)
        self.apply_main_visibility()
    def restore_main_workspace(self):
        state=self.store.state('main_workspace') or {};self.last_note_index=state.get('note_index',1);self.last_image_mode=state.get('image_mode',0)
        self.main_tabs.setCurrentIndex(state.get('tab',2 if self.note_mode else (0 if self.workspace_mode.currentData()=='disk' else 1)));self.change_main_tab(self.main_tabs.currentIndex())
    def save_main_workspace(self):
        self.store.state('main_workspace',{'tab':self.main_tabs.currentIndex(),'note_index':self.document_index if self.note_mode else self.last_note_index,'image_mode':self.last_image_mode})
    def save_image_to_note(self,disk=False):
        from .note_transfer import NoteTransferDialog
        self.save_draft()
        if disk:
            panel=self.disk_browser;path=panel.preview_path
            if not path or panel.viewer.pixmap_item is None:self.statusBar().showMessage('먼저 이미지 미리보기를 완료하세요.');return
            positive=panel.positive.toPlainText();negative=panel.negative.toPlainText();work=work_negative=tags=''
        else:
            if not self.path:self.statusBar().showMessage('먼저 이미지를 선택하세요.');return
            path=str(self.path);positive=self.info.get('positive','');negative=self.info.get('negative','');work=self.draft.toPlainText();work_negative=self.draft_negative.toPlainText();tags=self.tag_text()
        dialog=NoteTransferDialog(self,path,[('원본 프롬프트','prompt',positive,True),('원본 네거티브','negative',negative,True),('작업 프롬프트','prompt',work,False),('작업 네거티브','negative',work_negative,False),('추정 태그','prompt',tags,False)])
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.transferred_note=dialog.saved_id;self.refresh_notes();self.open_saved_note.show();self.statusBar().showMessage('노트에 저장했습니다. 현재 이미지 작업은 유지됩니다.',6000)
    def open_transferred_note(self):
        self.main_tabs.setCurrentIndex(2);self.open_note_id(self.transferred_note)
    def note_to_image(self):
        from PySide6.QtWidgets import QMessageBox
        if not self.path:self.statusBar().showMessage('이미지 라이브러리에서 대상 이미지를 먼저 여세요.');return
        prompt=self.draft.toPlainText();negative=self.draft_negative.toPlainText()
        box=QMessageBox(self);box.setWindowTitle('이미지 작업 프롬프트로 보내기');box.setText('대상: '+str(self.path));append=box.addButton('기존 내용에 추가',QMessageBox.ButtonRole.AcceptRole);replace=box.addButton('교체',QMessageBox.ButtonRole.ActionRole);box.addButton('취소',QMessageBox.ButtonRole.RejectRole);box.exec()
        if box.clickedButton() not in (append,replace):return
        self.main_tabs.setCurrentIndex(1)
        for editor,text in [(self.draft,prompt),(self.draft_negative,negative)]:
            cursor=editor.textCursor();cursor.beginEditBlock()
            if box.clickedButton() is replace:cursor.select(QTextCursor.SelectionType.Document);cursor.insertText(text)
            elif text:cursor.movePosition(QTextCursor.MoveOperation.End);cursor.insertText(('\n\n' if editor.toPlainText() else '')+text)
            cursor.endEditBlock()
        self.tabs.setCurrentIndex(1);self.save_draft()
