#!/usr/bin/env python

# Requires PyQt4 and python-netaddr
# sudo yum install -y PyQt4 python-netaddr

import sys

import netaddr
from PyQt4 import QtCore
from PyQt4 import QtGui


config_template = """# Config generated by undercloud wizard
# Use these values in undercloud.conf
local_ip = %(local_ip)s
local_interface = %(local_interface)s
network_cidr = %(network_cidr)s
masquerade_network = %(masquerade_network)s
dhcp_start = %(dhcp_start)s
dhcp_end = %(dhcp_end)s
discovery_iprange = %(discovery_start)s,%(discovery_end)s
network_gateway = %(network_gateway)s
"""


class InvalidConfiguration(Exception):
    pass


class PairWidget(QtGui.QWidget):
    def __init__(self, label, widget, parent = None):
        super(PairWidget, self).__init__(parent)

        self.layout = QtGui.QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.label = label
        try:
            self.layout.addWidget(self.label)
        except TypeError:
            self.label = QtGui.QLabel(label)
            self.layout.addWidget(self.label)

        self.widget = widget
        self.layout.addWidget(self.widget)


class MainForm(QtGui.QMainWindow):
    # FIXME(bnemec): Adding an arbitrary 5 to the node count, to allow
    # for virtual ips.  This may not be enough for some setups.
    virtual_ips = 5
    # local_ip, public_vip, admin_vip
    undercloud_ips = 3

    def __init__(self):
        super(MainForm, self).__init__()

        self._setup_ui()
        self._generate_advanced_values()
        self.show()

    def _setup_ui(self):
        self.resize(600, 300)
        self.setWindowTitle('Undercloud Config Wizard')

        self.setCentralWidget(QtGui.QWidget())
        main_layout = QtGui.QVBoxLayout()
        self.centralWidget().setLayout(main_layout)
        self.error_dialog = QtGui.QErrorMessage.qtHandler()
        self.error_dialog.setWindowTitle('Invalid Configuration')

        basic_group = QtGui.QGroupBox('Basic Settings')
        basic_layout = QtGui.QVBoxLayout(basic_group)
        main_layout.addWidget(basic_group)

        self.pxe_interface = QtGui.QLineEdit()
        self.pxe_interface.setText('eth1')
        basic_layout.addWidget(PairWidget('Provisioning Interface',
                                          self.pxe_interface))

        self.pxe_cidr = QtGui.QLineEdit()
        self.pxe_cidr.setText('192.0.2.0/24')
        basic_layout.addWidget(PairWidget('Provisioning CIDR',
                                          self.pxe_cidr))

        self.node_count = QtGui.QSpinBox()
        self.node_count.setValue(2)
        self.node_count.setMaximum(10000)
        basic_layout.addWidget(PairWidget('Overcloud Node Count',
                                          self.node_count))

        generate_advanced = QtGui.QPushButton('Generate Advanced')
        generate_advanced.setToolTip('Generate advanced option values based '
                                     'on the Basic values.')
        generate_advanced.clicked.connect(self._generate_advanced_values)
        main_layout.addWidget(generate_advanced)

        advanced_group = QtGui.QGroupBox('Advanced Settings')
        advanced_layout = QtGui.QVBoxLayout(advanced_group)
        main_layout.addWidget(advanced_group)

        advanced_message = ('The generated defaults are intended to work for '
                            'most deployments, but any of the values below '
                            'may be edited.')
        advanced_label = QtGui.QLabel(advanced_message)
        advanced_label.setWordWrap(True)
        advanced_label.setSizePolicy(QtGui.QSizePolicy.Preferred,
                                     QtGui.QSizePolicy.Preferred)
        advanced_label.setMaximumSize(99999, 99999)
        advanced_label.setMinimumSize(0, 50)
        advanced_layout.addWidget(advanced_label)

        # Allons-y!
        ood_message = ('<div style="color:#f00">Advanced values may be out '
                       'of date.  Regeneration recommended.</div>')
        self.ood = QtGui.QLabel(ood_message)
        self.ood.hide()
        self.pxe_cidr.textEdited.connect(self.ood.show)
        self.node_count.valueChanged.connect(self.ood.show)
        advanced_layout.addWidget(self.ood)

        self.local_ip = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Local IP',
                                             self.local_ip))
        self.network_gateway = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Network Gateway',
                                             self.network_gateway))

        self.dhcp_start = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Provisioning DHCP Start',
                                             self.dhcp_start))
        self.dhcp_end = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Provisioning DHCP End',
                                             self.dhcp_end))
        self.discovery_start = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Discovery DHCP Start',
                                             self.discovery_start))
        self.discovery_end = QtGui.QLineEdit()
        advanced_layout.addWidget(PairWidget('Discovery DHCP End',
                                             self.discovery_end))

        generate_config = QtGui.QPushButton('Generate Config')
        generate_config.clicked.connect(self._generate_config)
        main_layout.addWidget(generate_config)


    def _invalid_configuration(self, message):
        # This should be qCritical, but there seems to be a bug
        # in that on my version of Qt that makes it show as a debug
        # message instead of critical.
        QtCore.qWarning(message)
        raise InvalidConfiguration(message)

    def _validate_count(self, node_count, cidr_ips, extra_ips):
        """Verify the ips in cidr_ips are sufficient for node_count"""
        # node_count * 2 to allow for discovery range as well
        if len(cidr_ips) < node_count * 2 + extra_ips:
            message = 'Insufficient addresses available in provisioning CIDR'
            self._invalid_configuration(message)

    def _get_values(self):
        """Return a dict containing all UI values"""
        return {
            'local_ip': str(self.local_ip.text()),
            'local_interface': str(self.pxe_interface.text()),
            'network_cidr': str(self.pxe_cidr.text()),
            'masquerade_network': str(self.pxe_cidr.text()),
            'dhcp_start': str(self.dhcp_start.text()),
            'dhcp_end': str(self.dhcp_end.text()),
            'discovery_start': str(self.discovery_start.text()),
            'discovery_end': str(self.discovery_end.text()),
            'network_gateway': str(self.network_gateway.text()),
            'node_count': self.node_count.value(),
            }

    def _generate_advanced_values(self):
        values = self._get_values()
        cidr = netaddr.IPNetwork(values['network_cidr'])
        cidr_ips = list(cidr)
        node_count = values['node_count']
        self._validate_count(node_count, cidr_ips,
                             self.virtual_ips + self.undercloud_ips + 1)
        # 4 to allow room for two undercloud vips
        dhcp_start = 1 + self.undercloud_ips
        dhcp_end = dhcp_start + node_count + self.virtual_ips - 1
        discovery_start = dhcp_end + 1
        discovery_end = discovery_start + node_count - 1
        self._update_advanced_ui(cidr_ips, dhcp_start, dhcp_end,
                                 discovery_start, discovery_end)

    def _update_advanced_ui(self, cidr_ips, dhcp_start, dhcp_end,
                            discovery_start, discovery_end):
        """Method to isolate UI bits from the validation logic"""
        self.local_ip.setText(str(cidr_ips[1]))
        self.network_gateway.setText(str(cidr_ips[1]))
        self.dhcp_start.setText(str(cidr_ips[dhcp_start]))
        self.dhcp_end.setText(str(cidr_ips[dhcp_end]))
        self.discovery_start.setText(str(cidr_ips[discovery_start]))
        self.discovery_end.setText(str(cidr_ips[discovery_end]))
        self.ood.hide()

    def _generate_config(self):
        dialog = QtGui.QDialog(self)
        layout = QtGui.QVBoxLayout()
        dialog.setLayout(layout)
        dialog.resize(800, 600)
        config_text = QtGui.QTextEdit()
        layout.addWidget(config_text)

        params = self._get_values()
        self._validate_config(params)

        config_text.setText(config_template % params)

        dialog.show()

    def _validate_config(self, params):
        cidr = netaddr.IPNetwork(params['network_cidr'])
        cidr_ips = list(cidr)
        def validate_addr_in_cidr(params, name):
            if netaddr.IPAddress(params[name]) not in cidr_ips:
                message = ('%s "%s" not in defined CIDR "%s"' %
                           (name, params[name], cidr))
                self._invalid_configuration(message)
        validate_addr_in_cidr(params, 'local_ip')
        validate_addr_in_cidr(params, 'network_gateway')
        validate_addr_in_cidr(params, 'dhcp_start')
        validate_addr_in_cidr(params, 'dhcp_end')
        validate_addr_in_cidr(params, 'discovery_start')
        validate_addr_in_cidr(params, 'discovery_end')

        # Validate dhcp range
        dhcp_start = netaddr.IPAddress(params['dhcp_start'])
        dhcp_end = netaddr.IPAddress(params['dhcp_end'])
        dhcp_start_index = cidr_ips.index(dhcp_start)
        dhcp_end_index = cidr_ips.index(dhcp_end)
        if dhcp_start_index >= dhcp_end_index:
            message = ('Invalid dhcp range specified, dhcp_start "%s" does '
                       'not come before dhcp_end "%s"' %
                       (dhcp_start, dhcp_end))
            self._invalid_configuration(message)
        # Validate discovery range
        discovery_start = netaddr.IPAddress(params['discovery_start'])
        discovery_end = netaddr.IPAddress(params['discovery_end'])
        discovery_start_index = cidr_ips.index(discovery_start)
        discovery_end_index = cidr_ips.index(discovery_end)
        if discovery_start_index >= discovery_end_index:
            message = ('Invalid discovery range specified, discovery_start '
                       '"%s" does not come before discovery_end "%s"' %
                       (discovery_start, discovery_end))
            self._invalid_configuration(message)
        # Validate the provisioning and discovery ip ranges do not overlap
        if (discovery_start_index >= dhcp_start_index and
            discovery_start_index <= dhcp_end_index):
            message = ('Discovery DHCP range start "%s" overlaps provisioning '
                       'DHCP range.' % discovery_start)
            self._invalid_configuration(message)
        if (discovery_end_index >= dhcp_start_index and
            discovery_end_index <= dhcp_end_index):
            message = ('Discovery DHCP range end "%s" overlaps provisioning '
                       'DHCP range.' % discovery_start)
            self._invalid_configuration(message)



if __name__ == '__main__':
    app = QtGui.QApplication(sys.argv)

    form = MainForm()

    sys.exit(app.exec_())
