Hello everyone,

We're happy to announce the release of the Ansible 12.3.0 package!

Ansible 12.3.0 depends on ansible-core 2.19.5 and includes a curated set of Ansible collections that provide a vast number of modules, plugins, and roles.

How to get it
-------------

This release is available on PyPI and can be installed with pip:

```console
python3 -m pip install ansible==12.3.0 --user
```

The sources for this release can be found here:

Release tarball: https://files.pythonhosted.org/packages/d4/df/60253bfc1f87e3d5b52a06723cc15270428dab113a878cd162ab3923db4e/ansible-12.3.0.tar.gz

SHA256: `02721f6fb432ddd47f1044ac49b04b5e9ae08890bd427def8df3db1607aeec51`

Wheel package: https://files.pythonhosted.org/packages/dc/91/ed9ff629465050d4bdbc9da33d348156736b8778733f97a3627daae4f9ce/ansible-12.3.0-py3-none-any.whl

SHA256: `cd156f82fa87f7a899212b0efa9f7ca3a24d609212de9f78428a572eb01e5414`

Some important details
----------------------

ansible-core is a separate package on which ansible depends. `pip install ansible` installs `ansible-core`, but it can also be installed independently of the ansible package.

Collections that have opted to join the Ansible 12 unified changelog will have an entry on this page: https://github.com/ansible-community/ansible-build-data/blob/12.3.0/12/CHANGELOG-v12.md

For collections which have not opted-in to the unified changelog, you may find more information on https://docs.ansible.com/projects/ansible/latest/collections or on the collection source repository. For example, the community.crypto collection is available at https://docs.ansible.com/projects/ansible/latest/collections/community/crypto/index.html and you can find a link to the source repository under the “Repository (Sources)” button.

The changelog for ansible-core 2.19 installed by this release of Ansible 12 can be found here: https://github.com/ansible/ansible/blob/v2.19.5/changelogs/CHANGELOG-v2.19.rst

What's the schedule for new Ansible releases after 12.3.0?
----------------------------------------------------------

The next release roadmap can be found at https://docs.ansible.com/projects/ansible/devel/roadmap/ansible_roadmap_index.html

The Ansible community package release schedule follows the Ansible Core release schedule, including, for example, delays for holidays. This means Ansible releases happen every four weeks through most of the year, but release dates may be delayed when Ansible Core releases are.

Subscribe to the Bullhorn for all future release dates, announcements, and Ansible contributor community news. To subscribe, visit the [Bullhorn category in the forum](https://forum.ansible.com/c/news/bullhorn/17) and click the `bell` button at the right side. Then select `Watching`. You can find all past Bullhorn issues on the Ansible Community Forum at:

https://forum.ansible.com/c/news/bullhorn/17

Porting Help
------------

A unified porting guide for collections that have opted in is available here: https://docs.ansible.com/projects/ansible/devel/porting_guides/porting_guide_12.html

Getting collection updates from Ansible 12 with older releases of ansible-core
------------------------------------------------------------------------------

Ansible 12 depends on ansible-core 2.19. Depending on your needs, you can get collection updates as they ship in the Ansible “batteries included” package while continuing to use older versions of ansible-core.

See the ansible-galaxy requirements file based on the collections from Ansible 12 for this use case: https://github.com/ansible-community/ansible-build-data/blob/12.3.0/12/galaxy-requirements.yaml

After you download the requirements file, you can install the collections by running the following command:

```console
ansible-galaxy collection install -r galaxy-requirements.yaml
```

On behalf of the Ansible community, thank you and happy automating!

Cheers,
Ansible Release Management Working Group
