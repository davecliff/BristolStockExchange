

from matplotlib import pyplot as plot
import csv
import random






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

cy1 = 0;
cy2 = 0;
count = 0
for item in csv_reader:
    y1.append(int(float(item[5])))
    y2.append(int(float(item[17])))
    cy1 += int(float(item[5]))
    cy2 += int(float(item[17]))
    # y3.append(int(float(item[13])))
    # y4.append(int(float(item[17])))
    name1 = item[2]
    name2 = item[14]
    # name3 = item[10]
    # name4 = item[14]
    # print '%s,%s'%(item[5],item[9])
    count += 1
x = range(1,count+1)
fig, ax = plot.subplots()

cost1 = cy1/count
cost1_list = [cost1 for i in range(1,count+1)]

cost2 = cy2/count
cost2_list = [cost2 for i in range(1,count+1)]

ax.plot(x,y1,label="AA")
ax.plot(x,y2,label="IAA")
ax.plot(x,cost1_list,linestyle="dashed", label= "AA's average profit = "+str(float((cy1+0.0)/count)))
ax.plot(x,cost2_list,linestyle="dashed", label= "IAA's average profit = "+str(float((cy2+0.0)/count)))
# ax.plot(x,y3,label=name3)
# ax.plot(x,y4,label=name4)

# xticks_label  =  [i*5 for i in range(1,21)]
# plot.xticks( xticks_label)
# yticks_label  =  [i*5 for i in range(10,30)]
# plot.yticks( yticks_label)
ax.set_xlabel('trading day')
ax.set_ylabel('total profit in each trading day')
ax.legend()
plot.savefig("./line_chart.png")

