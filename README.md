# Overview

pyapi is a maintenance toolkit that allows your code to stay up to date on whatever python libs/apis you want automatically. it saves updates as a commit, so all you need to do is review and push. pyapi handles the update and hands you a clean commit to review!!!! :>

- pure python, no dependencies
- can configure most* libraries and apis
- llm is inside (only for checking changelogs)


## Installation

```bash
pip install pyapimaintenance
```

pyapi works autonomously and continously. all you need to do is run the initial command on your terminal. 

```bash
pyapimaintenance config
```
then, whenever you need to update api versions in your code:

```bash
pyapimaintenance startrun
```

this takes a sec, but pyapi will automatically change your codebase and commit it in your repo. it's up to you to decide if you want to push or roll back the commit. 

hope this makes everyones lives a little easier!!! :)
