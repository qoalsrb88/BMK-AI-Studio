import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QStringListModel
from PySide6.QtWidgets import QAbstractItemView,QApplication,QListView
from bmk_studio import shell_actions

app=QApplication.instance() or QApplication([])

class ShellActionTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(tempfile.mkdtemp(prefix='bmk-shell-'));self.file=self.root/'a, b.png';self.file.write_bytes(b'x')

    @unittest.skipUnless(os.name=='nt','Explorer command line is Windows-specific')
    def test_reveal_selects_file_and_opens_folder(self):
        with patch('bmk_studio.shell_actions.subprocess.Popen') as popen:
            self.assertTrue(shell_actions.reveal_in_explorer(self.file))
            self.assertTrue(shell_actions.reveal_in_explorer(self.root))
        self.assertEqual(popen.call_args_list[0].args[0],f'explorer /select,"{self.file}"')
        self.assertEqual(popen.call_args_list[1].args[0],f'explorer "{self.root}"')

    def test_missing_paths_do_nothing(self):
        missing=self.root/'gone.png'
        with patch('bmk_studio.shell_actions.subprocess.Popen') as popen,patch('bmk_studio.shell_actions.QDesktopServices.openUrl') as open_url:
            self.assertFalse(shell_actions.reveal_in_explorer(missing));self.assertFalse(shell_actions.open_default(missing))
        popen.assert_not_called();open_url.assert_not_called()

    def test_open_default_uses_file_url(self):
        with patch('bmk_studio.shell_actions.QDesktopServices.openUrl',return_value=True) as open_url:
            self.assertTrue(shell_actions.open_default(self.file))
        self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()),self.file)

    def test_copy_paths_and_names(self):
        other=self.root/'c.png'
        self.assertEqual(shell_actions.copy_paths([self.file,other]),2)
        self.assertEqual(QApplication.clipboard().text(),f'{self.file}\n{other}')
        shell_actions.copy_paths([self.file,other],names=True);self.assertEqual(QApplication.clipboard().text(),'a, b.png\nc.png')
        QApplication.clipboard().setText('kept');self.assertEqual(shell_actions.copy_paths([]),0);self.assertEqual(QApplication.clipboard().text(),'kept')

    def test_context_selection_follows_windows_convention(self):
        view=QListView();view.setModel(QStringListModel(['a','b','c']));view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        model=view.model();selection=view.selectionModel()
        selection.select(model.index(0,0),selection.SelectionFlag.Select);selection.select(model.index(1,0),selection.SelectionFlag.Select)
        shell_actions.select_for_context(view,model.index(1,0))
        self.assertEqual({i.row() for i in selection.selectedIndexes()},{0,1})
        shell_actions.select_for_context(view,model.index(2,0))
        self.assertEqual({i.row() for i in selection.selectedIndexes()},{2});self.assertEqual(view.currentIndex().row(),2)
        shell_actions.select_for_context(view,model.index(-1,0));self.assertEqual({i.row() for i in selection.selectedIndexes()},{2})

if __name__=='__main__':unittest.main()
