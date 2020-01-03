# Testing

I've been using a Vagrant box and pyenv. All testing takes place in the `/vagrant` folder on the Vagrant box, so after you ssh into the vagrant box:

```
$ cd /vagrant
```


## Running tests in Python 3

```
$ pyenv versions
$ pyenv shell <INSTALLED_PYTHON_3_VERSION>
$ python --version
$ pyt3 -d
```


## Running tests in Python 2

```
$ pyenv versions
$ pyenv shell <INSTALLED_PYTHON_2_VERSION>
$ python --version
$ pyt2 -d
```