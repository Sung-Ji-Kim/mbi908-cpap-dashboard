import subprocess

pipelines = ["A","B"]
levels =["None","Low","Medium","High"]
# seeds = range(1,2) #for test: 1time
seeds = range(1,11)

for p in pipelines:
    for lv in levels:
        for s in seeds:
            print("running",p,lv,s)
            subprocess.run(
                ["python","run.py","--pipeline",p,"--level",lv,"--seed",str(s)],
                check = True,
            )

