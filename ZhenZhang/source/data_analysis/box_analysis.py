

import numpy as np
import matplotlib.pyplot as plt
import csv
from pylab import *


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
cy3 = 0;
cy4 = 0;
count = 0
for item in csv_reader:
    y1.append(int(float(item[5])))
    # y2.append(int(float(item[13])))
    y3.append(int(float(item[17])))
    #y4.append(int(float(item[21])))




fig, (ax1, ax2) = plt.subplots(nrows=1, ncols=2, figsize=(10, 8))


data = [y1,y3]
names = ['AA','IAA']


ax1.set_title('(a) The daily profits for different agents')
green_diamond = dict(markerfacecolor='g', marker='D')
dp1= ax1.boxplot(data,vert=True,whis=0.75,notch=False, labels=names,showmeans=True,meanline=False,meanprops=green_diamond)




x1,y = dp1['medians'][0].get_xydata()[1]
ax1.text(x1+0.075, y, '%.1f' % y,horizontalalignment='left')
x2,y = dp1['medians'][1].get_xydata()[1]
ax1.text(x2+0.075, y, '%.1f' % y,horizontalalignment='left')

for index in range(len(dp1['means'])):
    y = dp1['means'][index].get_ydata()[0]
    if index==0:
        ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')



for index in range(len(dp1['boxes'])):
    y = dp1['boxes'][index].get_ydata()[0]
    if index==0:
        ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')

    y = dp1['boxes'][index].get_ydata()[2]
    if index==0:
        ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    # elif index ==1:
    #     ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')


# for index in range(len(dp1['boxes'])):
#
#     y = dp1['boxes'][index].get_ydata()[0]
#
#     if index==0:
#         ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
#     elif index ==1:
#         ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')
#
#     y = dp1['boxes'][index].get_ydata()[2]
#
#     if index==0:
#         ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
#     elif index ==1:
#         ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')


for index in range(len(dp1['caps'])):

    y = dp1['caps'][index].get_ydata()[0]
    if index==0:
        ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==2:
        ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==3:
        ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')

    # y = dp1['caps'][index].get_ydata()[1]
    # print 'top'
    # print y
    # if index==0:
    #     ax1.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    # elif index ==1:
    #     ax1.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')
# for line in dp1['means']:
#     # get position data for median line
#     x, y = line.get_ydata()[0] # top of median line
#     # overlay median value
#     print x
#     print y
#     ax1.text(x+0.125, y, '%.1f' % y,horizontalalignment='left')
#
# print 'boxes'
#
# for line in dp1['boxes']:
#
#     x, y = line.get_xydata()[0] # bottom of left line
#     ax1.text(x+0.125,y, '%.1f' % y,horizontalalignment='right')      # below
#     x, y = line.get_xydata()[2] # bottom of right line
#     ax1.text(x+0.125,y, '%.1f' % y,horizontalalignment='right')      # below




dif1 = []
for i in range(len(y1)):
    dif1.append(y3[i]-y1[i])


ax2.set_title('(b) The profit differences for different agents')
dp2 = ax2.boxplot(dif1,vert=True,whis=0.75,notch=False, showmeans=True,labels=['IAA-AA'],meanprops=green_diamond)

x1,y = dp2['medians'][0].get_xydata()[1]
ax2.text(x1+0.075, y, '%.1f' % y,horizontalalignment='left')


for index in range(len(dp2['means'])):
    y = dp2['means'][index].get_ydata()[0]
    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')



for index in range(len(dp2['boxes'])):
    y = dp2['boxes'][index].get_ydata()[0]
    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')

    y = dp2['boxes'][index].get_ydata()[2]
    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')


for index in range(len(dp2['boxes'])):

    y = dp2['boxes'][index].get_ydata()[0]

    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')

    y = dp2['boxes'][index].get_ydata()[2]

    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')


for index in range(len(dp2['caps'])):
    y = dp2['caps'][index].get_ydata()[0]
    if index==0:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==1:
        ax2.text(x1 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==2:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')
    elif index ==3:
        ax2.text(x2 + 0.075, y, '%.1f' % y, horizontalalignment='left')




plt.savefig("./box.png")


# # fake up some data
# spread = np.random.rand(50) * 100
# center = np.ones(25) * 50
# flier_high = np.random.rand(10) * 100 + 100
# flier_low = np.random.rand(10) * -100
# data = np.concatenate((spread, center, flier_high, flier_low))
#
# fig1, ax1 = plt.subplots()
# ax1.set_title('Basic Plot')
# ax1.boxplot(data,vert=False)
#
#
# spread = np.random.rand(50) * 100
# center = np.ones(25) * 40
# flier_high = np.random.rand(10) * 100 + 100
# flier_low = np.random.rand(10) * -100
# d2 = np.concatenate((spread, center, flier_high, flier_low))
# data.shape = (-1, 1)
# d2.shape = (-1, 1)
#
# data = [data, d2, d2[::2,0]]
# fig7, ax7 = plt.subplots()
# ax7.set_title('Multiple Samples with Different sizes')
# ax7.boxplot(data,vert=False)
#
# plt.show()