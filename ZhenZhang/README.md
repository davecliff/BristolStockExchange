This folder holds the source code developed by Zhen Zhang as part of his MSc project, supervised by Dave Cliff, at the University of Bristol, submitted in September 2020.

-----

The main contribution is to adapt the multi-level order flow imbalance (MLOFI) to IAA and test it under multiple scenarios.

It includes two modules:

+ "impact-sensitive" module

+ "evaluation" module

  

For the "impact-sensitive" module, the MLOFI is used to capture imbalances in the market. We can set the variable, **m** which determines how depth IAA observes.  The core function is ***imbalance_alter()***. 

For the "evaluation" module, the imbalance ratio is used to filter out some insignificant imbalances. The core function is ***is_imbalance_significant().***

-----



In [IAA_MLOFI.py](./source/IAA_MLOFI.py), it is  the IAA with the "impact-sensitive" module.

In [IAA_NEW.py](./source/IAA_NEW.py), it is the IAA with two modules.

In [IZIP_MLOFI.py](./source/IZIP_MLOFI.py), it is the ZZIZIP.

In [ZZISHV.py](./source/ZZISHV.py), it is the ZZISHV.

[Mybalances.csv](./source/Mybalances.csv) shows the average aggregate profit of the different types of traders in the market for each trading day.

[Mytapes.csv](./source/Mytapes.csv) records the history of transactions in the market. 

[hypothesis_test.py](./source/data_analysis/hypothesis_test.py) shows the result of the mann-whitney u test and confidence intervals.

[box_analysis.py](./source/data_analysis/box_analysis.py) draws the box and whisker plot.

----

Please see more details in the dissertation (available soon).

