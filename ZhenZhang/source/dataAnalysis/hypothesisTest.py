


import scipy.stats as stats
import csv
csv_file = open("../Mybalances.csv","r")
csv_reader = csv.reader(csv_file);

y1 = []
y2 = []
y3 = []
y4 = []
name1 = None
name2 = None
name3 = None
name4 = None


count = 0
for item in csv_reader:
    y1.append(float(item[5]))
    y2.append(float(item[17]))
    # y3.append(int(float(item[13])))
    # y4.append(int(float(item[17])))
    name1 = item[2]
    name2 = item[14]
    # name3 = item[10]
    # name4 = item[14]
    # print '%s,%s'%(item[5],item[9])
    count += 1


u_statistic, pVal = stats.mannwhitneyu(y1, y2,alternative='less')

print "u_statistic is %f"%u_statistic;
print "p value is %f"%pVal;


import numpy as np
#create 95% confidence interval for population mean weight
print np.mean(y2)
print stats.t.interval(alpha=0.95, df=len(y2)-1, loc=np.mean(y2), scale=stats.sem(y2))[1] - np.mean(y2)
print ""
print np.mean(y1)
print stats.t.interval(alpha=0.95, df=len(y1)-1, loc=np.mean(y1), scale=stats.sem(y1))[1] - np.mean(y1)
print ""

df = []

for index in range(len(y1)):
    df.append(y2[index]-y1[index])
print np.mean(df)
print stats.t.interval(alpha=0.95, df=len(df)-1, loc=np.mean(df), scale=stats.sem(df))[1] - np.mean(df)

