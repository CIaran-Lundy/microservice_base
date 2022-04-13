from setuptools import setup, find_packages

setup(name='qpcrfrontend',
      version='1.0',
      packages=find_packages(where="app"),
      license='none',
      description='package for dash qpcr frontend ',
      #install_requires=['argparse',
      #                  'Bio',
      #                  'dash', 'dash_bio', 'dash_bootstrap_components', 'dash_core_components',
      #                  'dash_cytoscape', 'dash_html_components',
      #                  'entrezpy',
      #                  'jsonpickle',
      #                  'networkx',
      #                  'pandas', 'plotly'],
      url='https://github.com/youseq/qpcr_frontend',
      author='CIARAN_LUNDY',
      author_email='ciaran.lundy@youseq.com'
     )
