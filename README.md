# Research_Prepare


##### If haven't ```research_env``` like custtom conda vertural enviroment then create new conda enviroment

>- create 

```bash
    conda create -n research_env python=3.10 -y
```

>- activate 

```bash
    conda activate research_env
```

>- deactivate

```bash
    conda research_env
```

>- if you want to see your conda vertual enviroment list then run:
```bash
conda env list
```

##### After activating ```research_env``` and exicute requirements.txt file
```bash
pip install -r requirements.txt
```

```bash
conda install -c conda-forge gdal
```