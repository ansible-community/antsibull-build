Hello everyone,

We're happy to announce the release of the Ansible 12.0.0b1 package pre-release!

Ansible 12.0.0b1 depends on ansible-core 2.19.0 and includes a curated set of Ansible collections that provide a vast number of modules, plugins, and roles. This is a pre-release of Ansible 12.

How to get it
-------------

This pre-release is available on PyPI and can be installed with pip:

```console
python3 -m pip install ansible==12.0.0b1 --user
```

The sources for this release can be found here:

Release tarball: https://files.pythonhosted.org/packages/f1/f5/69eac93df7488324bcb8e69d666e7ae7ed7a305711626871f4975800d743/ansible-12.0.0b1.tar.gz

SHA256: `1a5f15dca693dc5f058da79415a1a4870e4c28769e42cbf4572ac3827bf9570a`

Wheel package: https://files.pythonhosted.org/packages/c8/50/965b1807e514e6ae9f7bb091bf5ad9e6899b8b9875aff6c797473bd9bd36/ansible-12.0.0b1-py3-none-any.whl

SHA256: `2ba62e2f7480189d78d0e870d9bea29ebc2dfdd4db9a36f9707dbe48ca8b03a7`

Some important details
----------------------

ansible-core is a separate package on which ansible depends. `pip install ansible` installs `ansible-core`, but it can also be installed independently of the ansible package.

Collections that have opted to join the Ansible 12 unified changelog will have an entry on this page: https://github.com/ansible-community/ansible-build-data/blob/12.0.0b1/12/CHANGELOG-v12.md

For collections which have not opted-in to the unified changelog, you may find more information on https://docs.ansible.com/projects/ansible/latest/collections or on the collection source repository. For example, the community.crypto collection is available at https://docs.ansible.com/projects/ansible/latest/collections/community/crypto/index.html and you can find a link to the source repository under the “Repository (Sources)” button.

The changelog for ansible-core 2.19 installed by this release of Ansible 12 can be found here: https://github.com/ansible/ansible/blob/v2.19.0/changelogs/CHANGELOG-v2.19.rst

What's the schedule for new Ansible releases after 12.0.0b1?
------------------------------------------------------------

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

See the ansible-galaxy requirements file based on the collections from Ansible 12 for this use case: https://github.com/ansible-community/ansible-build-data/blob/12.0.0b1/12/galaxy-requirements.yaml

After you download the requirements file, you can install the collections by running the following command:

```console
ansible-galaxy collection install -r galaxy-requirements.yaml
```

On behalf of the Ansible community, thank you and happy automating!

Cheers,
Ansible Release Management Working Group
