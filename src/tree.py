#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""© Ihor Mirzov, 2019-2021
Distributed under GNU General Public License v3.0

Methods to work with main window treeView widget.
"""

# Standard modules
import re
import os
import sys
import logging

# External modules
from PyQt5 import QtWidgets, QtCore, QtGui, QtWebEngineWidgets

# My modules
import gui
import path
import settings
import model
from model.kom import ItemType, Implementation
import tests


class Tree:
    """
    f - Window Factory
    m - Model
    """

    def __init__(self, f, m):
        self.f = f
        self.m = m
        self.model = QtGui.QStandardItemModel()
        self.f.mw.treeView.setModel(self.model)

    def keyPressEvent(self, e):
        """Delete keyword implementation in the
        treeView by pressing 'Delete' button.
        """
        if e.key() == QtCore.Qt.Key_Delete:
            self.actionDeleteImplementation()

    def generateTreeView(self, m):
        """Recursively generate treeView widget items based on KOM."""
        self.model.clear() # remove all items and data from tree
        parent_element = self.model.invisibleRootItem() # top element in QTreeView
        self.addToTree(parent_element, self.m.KOM.root.items) # pass top level groups

    def addToTree(self, parent_element, items):
        """Used with generateTreeView() - implements recursion."""
        for item in items:

            # Add to the tree only needed item_types
            allowed = [ItemType.GROUP, ItemType.KEYWORD,
                ItemType.IMPLEMENTATION]
            if item.itype not in allowed:
                continue

            # Check if there are keywords with implementations
            if not settings.s.show_empty_keywords \
                and not item.count_implementations() \
                and item.itype != ItemType.IMPLEMENTATION:
                continue

            # Create tree_element
            tree_element = QtGui.QStandardItem(item.name)
            tree_element.setData(item)
            parent_element.appendRow(tree_element)

            # Set text color for tree_element
            brush = QtGui.QBrush()
            brush.setColor(QtCore.Qt.gray)
            if item.is_active():
                brush.setColor(QtCore.Qt.black)
                # Bold font for implementations
                if item.itype == ItemType.IMPLEMENTATION:
                    font = QtGui.QFont()
                    font.setBold(True)
                    tree_element.setFont(font)
            tree_element.setForeground(brush)

            # Expand / collapse
            if item.expanded:
                self.f.mw.treeView.expand(tree_element.index())
            else:
                self.f.mw.treeView.collapse(tree_element.index())

            # Add icon to each keyword in tree
            icon_name = item.name.replace('*', '') + '.png'
            icon_name = icon_name.replace(' ', '_')
            icon_name = icon_name.replace('-', '_')
            icon_path = os.path.join(path.p.img, 'icon_' + icon_name.lower())
            icon = QtGui.QIcon(icon_path)
            tree_element.setIcon(icon)

            # Organize recursion
            impls = item.get_implementations()
            if len(impls):
                self.addToTree(tree_element, impls)
            else:
                self.addToTree(tree_element, item.items)

    def doubleClicked(self):
        """Double click on treeView item: edit the keyword via dialog."""
        index = self.f.mw.treeView.selectedIndexes()[0] # selected item index
        tree_element = self.model.itemFromIndex(index) # treeView item obtained from 'index'
        item = tree_element.data() # now it is GROUP, KEYWORD or IMPLEMENTATION

        # Double click on GROUP doesn't create dialog
        allowed_types = [ItemType.KEYWORD, ItemType.IMPLEMENTATION]
        if not item or item.itype not in allowed_types:
            return

        if not item.active:
            kw_name = item.get_parent_keyword_name()
            msg = 'Please, create {} first.'.format(kw_name)
            logging.warning(msg)
            return

        # Exec dialog and recieve answer
        f = gui.window.Factory()

        # Process response from dialog window if user pressed 'OK'
        if f.run_master_dialog(self.m.KOM, item): # 0 = cancel, 1 = ok

            # The generated piece of .inp code for the CalculiX input file
            inp_code = f.mw.ok() # list of strings

            # Create implementation object for keyword
            if item.itype == ItemType.KEYWORD:
                impl = Implementation(item, inp_code) # create keyword implementation

                # Regenerate tree_element children
                tree_element.removeRows(0, tree_element.rowCount()) # remove all children
                self.addToTree(tree_element, item.get_implementations()) # add only implementations

                # Reparse mesh or constraints
                # self.m.Mesh.reparse(inp_code)
                reparsed = model.parsers.mesh.Mesh(icode=inp_code, old=self.m.Mesh)
                if self.m.Mesh is not None:
                    self.m.Mesh.updateWith(reparsed)
                self.clicked() # rehighlight

            # Replace implementation object with a new one
            elif item.itype == ItemType.IMPLEMENTATION:
                # Remove old one
                parent = tree_element.parent() # parent treeView item
                keyword = parent.data() # parent keyword for implementation
                keyword.items.remove(item) # remove implementation from keyword items

                # Add new one
                impl = Implementation(keyword, inp_code, name=item.name)
                tree_element.setData(impl)

                # Reparse mesh or constraints
                reparsed = model.parsers.mesh.Mesh(icode=inp_code, old=self.m.Mesh)
                self.m.Mesh.updateWith(reparsed)
                self.clicked() # rehighlight

    def clicked(self):
        """Highlight node sets, element sets or surfaces."""

        # Debug for Ctrl+Click
        if not len(self.f.mw.treeView.selectedIndexes()):
            return

        # Highlight only when INP is opened
        if self.f.sw is None:
            return
        if not (path.p.path_cgx + ' -c ') in self.f.sw.cmd:
            return

        index = self.f.mw.treeView.selectedIndexes()[0] # selected item index
        tree_element = self.model.itemFromIndex(index) # treeView item obtained from 'index'
        item = tree_element.data() # now it is GROUP, KEYWORD or IMPLEMENTATION

        # Highlight entities
        if item and item.itype == ItemType.IMPLEMENTATION:
            ipn_up = item.parent.name.upper()
            _set = []

            i = 0
            while item.inp_code[i].startswith('**'):
                i += 1
            lead_line = item.inp_code[i]

            # Highlight mesh entities
            if ipn_up == '*NSET' or ipn_up == '*NODE':
                match = re.search('NSET\s*=\s*([\w\!\#\%\$\&\"\'\(\)\*\=\+\-\.\/\:\;\<\>\?\@\[\]\^\_\`\{\\\|\}\~]*)', lead_line.upper())
                if match: # if there is NSET attribute
                    name = lead_line[match.start(1):match.end(1)] # node set name
                    if name in self.m.Mesh.nsets:
                        self.f.connection.post('plot n ' + name)

            elif ipn_up == '*ELSET' or ipn_up == '*ELEMENT':
                match = re.search('ELSET\s*=\s*([\w\!\#\%\$\&\"\'\(\)\*\=\+\-\.\/\:\;\<\>\?\@\[\]\^\_\`\{\\\|\}\~]*)', lead_line.upper())
                if match: # if there is ELSET attribute
                    name = lead_line[match.start(1):match.end(1)] # element set name
                    if name in self.m.Mesh.elsets:
                        self.f.connection.post('plot e ' + name)

            elif ipn_up == '*SURFACE':

                # Surface type - optional attribute
                stype = 'ELEMENT' # 'ELEMENT' or 'NODE'
                match = re.search('\*SURFACE\s*,.*TYPE\s*=\s*(\w*)', lead_line.upper())
                if match:
                    stype = lead_line[match.start(1):match.end(1)]

                match = re.search('NAME\s*=\s*([\w\!\#\%\$\&\"\'\(\)\*\=\+\-\.\/\:\;\<\>\?\@\[\]\^\_\`\{\\\|\}\~]*)', lead_line.upper())
                name = lead_line[match.start(1):match.end(1)] # surface name
                if stype == 'ELEMENT':
                    self.f.connection.post('plot f ' + name)
                elif stype=='NODE':
                    self.f.connection.post('plot f ' + name)

            # Highlight Loads & BC
            elif ipn_up in ['*BOUNDARY', '*CLOAD', '*CFLUX']:
                for line in item.inp_code[1:]:
                    line = line.strip()
                    n = line.replace(',', ' ').split()[0]
                    try:
                        # Single node number
                        _set.append(int(n))
                    except ValueError as err:
                        # Nodes in node set
                        _set.extend([n.num for n in self.m.Mesh.nsets[n].items])
                        pass
                # self.f.mw.VTK.highlight(set(_set), 1) # 1 = vtk.vtkSelectionNode.POINT

        # else:
        #     self.f.mw.deselect_cgx_sets()

    def rightClicked(self):
        """Context menu for right click."""
        self.myMenu = QtWidgets.QMenu('Menu', self.f.mw.treeView)

        try:
            index = self.f.mw.treeView.selectedIndexes()[0] # selected item index
            tree_element = self.model.itemFromIndex(index) # treeView item obtained from 'index'
            item = tree_element.data() # now it is GROUP, KEYWORD or IMPLEMENTATION

            # Context menu for any keyword and implementations
            if item:
                if item.itype == ItemType.IMPLEMENTATION:

                    # 'Edit' action
                    action_edit_implementation = QtWidgets.QAction('Edit', self.f.mw.treeView)
                    self.myMenu.addAction(action_edit_implementation)
                    action_edit_implementation.triggered.connect(self.doubleClicked)

                    # 'Delete' action
                    action_delete_implementation = QtWidgets.QAction('Delete', self.f.mw.treeView)
                    self.myMenu.addAction(action_delete_implementation)
                    action_delete_implementation.triggered.connect(self.actionDeleteImplementation)

                if item.itype == ItemType.KEYWORD:

                    # 'Create' action
                    action_create_implementation = QtWidgets.QAction('Create', self.f.mw.treeView)
                    self.myMenu.addAction(action_create_implementation)
                    action_create_implementation.triggered.connect(self.doubleClicked)

            # Add splitter
            self.myMenu.addSeparator()

        except IndexError:
            pass

        # Context menu elements which always present
        if settings.s.show_empty_keywords:
            action_show_hide = QtWidgets.QAction('Hide empty containers', self.f.mw.treeView)
        else:
            action_show_hide = QtWidgets.QAction('Show empty containers', self.f.mw.treeView)
        self.myMenu.addAction(action_show_hide)
        action_show_hide.triggered.connect(self.actionShowHide)

        action_collapse_expand = QtWidgets.QAction('Collapse/expand all', self.f.mw.treeView)
        self.myMenu.addAction(action_collapse_expand)
        action_collapse_expand.triggered.connect(self.action_collapse_expand_all)

        self.myMenu.exec_(QtGui.QCursor.pos())

    def actionShowHide(self):
        """Show/Hide empty treeView items."""
        settings.s.show_empty_keywords = not(settings.s.show_empty_keywords)
        settings.s.save() # save 'show_empty_keywords' value in settings
        self.generateTreeView(self.m)

    def action_collapse_expand_all(self):
        """Expand or collapse all treeView items."""
        if settings.s.expanded:
            self.f.mw.treeView.collapseAll()
        else:
            self.f.mw.treeView.expandAll()
        settings.s.expanded = not settings.s.expanded
        settings.s.save()

    def actionDeleteImplementation(self):
        """Delete keyword implementation from KOM."""

        def hide_parent(tree_element):
            # To hide current item/brunch it should be empty 'keyword' or 'group'
            if not settings.s.show_empty_keywords \
                and not tree_element.hasChildren() \
                and tree_element.data().itype != ItemType.IMPLEMENTATION:

                # Hide current item/brunch from tree via calling parent.removeRow
                parent = tree_element.parent()
                if not parent:
                    parent = self.model.invisibleRootItem()
                parent.removeRow(tree_element.row())

                if parent != self.model.invisibleRootItem():
                    hide_parent(parent)

        index = self.f.mw.treeView.selectedIndexes()[0] # selected item index
        tree_element = self.model.itemFromIndex(index) # treeView item obtained from 'index'
        item = tree_element.data() # now it is GROUP, KEYWORD or IMPLEMENTATION

        if item and item.itype == ItemType.IMPLEMENTATION:

            # Confirmation dialog to delete implementation
            answer = QtWidgets.QMessageBox.question(None,
                item.name, 'OK to delete ' + item.name + '?',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes)

            # If confirmed
            if answer == QtWidgets.QMessageBox.Yes:

                parent = tree_element.parent() # parent treeView item
                keyword = parent.data() # parent keyword for implementation
                keyword.items.remove(item) # remove implementation from keyword items

                # Regenerate parent children
                parent.removeRows(0, parent.rowCount()) # remove all children
                self.addToTree(parent, keyword.items)

                if not settings.s.show_empty_keywords:
                    hide_parent(parent)

    def expanded_or_collapsed(self, index):
        """Change KOM item 'expanded' variable when user interacts with treeView."""
        tree_element = self.model.itemFromIndex(index) # treeView item obtained from 'index'
        item = tree_element.data() # now it is GROUP, KEYWORD or IMPLEMENTATION
        if item:
            item.expanded = not item.expanded


@tests.test_wrapper()
def test():
    """Start keyword editor and generate the tree."""
    import log
    log.stop_logging()

    # Create application
    app = QtWidgets.QApplication(sys.argv)

    # Show main window
    f = gui.window.Factory()
    f.run_master()

    # Generate FEM model
    m = model.Model()

    # Create treeView items based on KOM
    t = Tree(f, m)

    # Actions
    f.mw.treeView.doubleClicked.connect(t.doubleClicked)
    f.mw.treeView.clicked.connect(t.clicked)
    f.mw.treeView.customContextMenuRequested.connect(t.rightClicked)
    f.mw.treeView.expanded.connect(t.expanded_or_collapsed)
    f.mw.treeView.collapsed.connect(t.expanded_or_collapsed)

    logging.disable() # switch off logging
    m.KOM = model.kom.KOM()
    logging.disable(logging.NOTSET) # switch on logging
    t.generateTreeView(m)

    # Execute application
    app.exec()


if __name__ == '__main__':
    test() # run test
