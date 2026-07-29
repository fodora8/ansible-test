# KVM guest HTML report

This Ansible playbook connects to one or more physical KVM/libvirt servers,
collects every configured guest (running or stopped), and creates one
single-column HTML report. Each VM shows:

- configured virtual CPUs
- assigned memory
- total virtual disk capacity
- each disk's target, capacity, and backing source

## Requirements

On the Ansible controller:

- `ansible-core`
- Python 3

On each KVM host:

- Python 3
- `virsh`
- permission to connect to `qemu:///system` (the playbook uses `become: true`)

No external Ansible collection is required.

## Configure and run

Edit `inventory.ini` and replace the example host:

```ini
[kvm_hosts]
kvm01 ansible_host=192.0.2.10 ansible_user=ansible
kvm02 ansible_host=192.0.2.11 ansible_user=ansible
```

Then run:

```shell
ansible-playbook -i inventory.ini kvm_report.yml
```

The report is written to `output/kvm-guests.html`.

To select a different libvirt connection or output location:

```shell
ansible-playbook -i inventory.ini kvm_report.yml \
  -e 'libvirt_uri=qemu:///system' \
  -e 'report_output_path=/tmp/kvm-guests.html'
```

Disk capacity comes from `virsh domblkinfo`. A disk is displayed as `Unknown`
when libvirt cannot report its capacity, for example when remote backing
storage is unavailable.
