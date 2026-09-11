# pyapimaintenance

pyapimaintenance is a maintenance package that allows your code to stay up to date on whatever python libs/apis you want automatically. it saves updates as a commit, so all you need to do is review and push. pyapimaintenance handles the update and hands you a clean commit to review!!!! :>

- can configure most* libraries and apis
- llm necessary (only for checking changelogs)


## install
to run this, you need a groq api key. groq is completely free and it takes like 1 min to set up: https://console.groq.com/home 

inital pip install:

```bash
pip install pyapimaintenance
```



## usage

```bash
export GROQ_API_KEY=...
```
first, run config

```bash
pyapimaintenance config
```
then:

```bash   
pyapimaintenance startrun
```
if you want autonomous ci when changelogs get updated, add:
```bash
pyapimaintenance update
```

## how it works

- `config` reads your `requirements.txt`, checks each library's latest PyPI version, and for anything newer,
  pulls the changelog and asks an LLM to propose migration rules (stored in `rules/<library>/rules.yaml`).

- `startrun` applies every rule under `rules/` across your repo, runs your tests to verify nothing broke, and commits the result on a separate branch!!!

- `update` allows a ci cycle to run weekly, which checks for changelog updates and automatically resolves them. 


 `.github/workflows/nightly-migration.yml.example` for a template to automate this on a schedule.

hope this is helpful for everyone~!!!! 

*btw this is still getting updates and fixes every few weeks, cherie and i are the sole contributors. 
