.. _install-amazon-linux-2022:

===================================
Installing Red on Amazon Linux 2022
===================================

.. include:: _includes/linux-preamble.rst

-------------------------------
Installing the pre-requirements
-------------------------------

Amazon Linux 2022 has all required packages available in official repositories. Install
them with dnf:

.. prompt:: bash

    sudo dnf -y install python39 git java-11-openjdk-headless @development-tools nano

.. Include common instructions:

.. include:: _includes/create-env-with-venv.rst

.. include:: _includes/install-and-setup-red-unix.rst
