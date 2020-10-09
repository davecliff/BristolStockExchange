from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math

bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies

class Trader_Simple_MLOFI(Trader):

    def __init__(self, ttype, tid, balance, time,m):

        Trader.__init__(self, ttype, tid, balance, time)

        self.limit = None
        self.job = None


        # variable for MLOFI
        self.last_lob = None;
        self.es_list = [];
        self.ds_list = [];

        #variable
        self.m = m;

    def calc_level_n_e(self, current_lob, n):
        b_n = 0
        r_n = 0
        a_n = 0
        q_n = 0

        b_n_1 = 0
        r_n_1 = 0
        a_n_1 = 0
        q_n_1 = 0

        if (len(current_lob['bids']['lob']) < n):
            b_n = 0
            r_n = 0
        else:
            b_n = current_lob['bids']['lob'][n - 1][0]
            r_n = current_lob['bids']['lob'][n - 1][1]

        if (len(self.last_lob['bids']['lob']) < n):
            b_n_1 = 0
            r_n_1 = 0
        else:
            b_n_1 = self.last_lob['bids']['lob'][n - 1][0]
            r_n_1 = self.last_lob['bids']['lob'][n - 1][1]

        if (len(current_lob['asks']['lob']) < n):
            a_n = 0
            q_n = 0
        else:
            a_n = current_lob['asks']['lob'][n - 1][0]
            q_n = current_lob['asks']['lob'][n - 1][1]

        if (len(self.last_lob['asks']['lob']) < n):
            a_n_1 = 0
            q_n_1 = 0
        else:
            a_n_1 = self.last_lob['asks']['lob'][n - 1][0]
            q_n_1 = self.last_lob['asks']['lob'][n - 1][1]

        delta_w = 0;

        if (b_n > b_n_1):
            delta_w = r_n
        elif (b_n == b_n_1):
            delta_w = r_n - r_n_1
        else:
            delta_w = -r_n_1

        delta_v = 0
        if (a_n > a_n_1):
            delta_v = -q_n_1
        elif (a_n == a_n_1):
            delta_v = q_n - q_n_1
        else:
            delta_v = q_n

        return delta_w - delta_v

    def calc_es(self, lob, m, verbose):
        new_e = {}
        for i in range(1, m + 1):
            new_e['level' + str(i)] = self.calc_level_n_e(lob, i)

        self.es_list.append(new_e)

    def calc_ds(self, lob, m, verbose):
        new_d = {}

        for i in range(1, m + 1):
            new_d['level' + str(i)] = self.cal_depth_n(lob, i)

        self.ds_list.append(new_d)

    def cal_depth_n(self, lob, n):

        if (len(lob['bids']['lob']) < n):
            r_n = 0
        else:
            r_n = lob['bids']['lob'][n - 1][1]

        if (len(lob['asks']['lob']) < n):
            q_n = 0
        else:
            q_n = lob['asks']['lob'][n - 1][1]
        return (r_n + q_n) / 2


    def getorder(self, time, countdown, lob, verbose):
        if len(self.orders) < 1:
            self.active = False
            return None
        else:
            self.limit = self.orders[0].price
            otype = self.orders[0].atype
            self.job = self.orders[0].atype
            ostyle = self.orders[0].astyle
            if otype == 'Bid':
                if(lob['midprice'] != None and lob['midprice']<self.limit):
                    quoteprice = lob['midprice']

                elif lob['bids']['n'] > 0:
                    quoteprice = lob['bids']['bestp']
                    if quoteprice > self.limit:
                        quoteprice = self.limit
                else:
                    quoteprice = self.limit
            else:
                if(lob['midprice'] != None and lob['midprice']>self.limit):
                    quoteprice = lob['midprice']
                elif lob['asks']['n'] > 0:
                    quoteprice = lob['asks']['bestp']
                    if quoteprice < self.limit:
                        quoteprice = self.limit
                else:
                    quoteprice = self.limit


            def imbalance_alter(quoteprice, lob, countdown, m):

                mlofi_list = [0 for i in range(m)]
                cd_list = [0 for i in range(m)]
                ad_list = []
                n = 1

                while len(self.es_list) >= n:
                    for i in range(m):
                        mlofi_list[i] += self.es_list[-n]['level' + str(i+1)]
                    n += 1
                    if n >= 11:
                        break

                n = 1

                while len(self.ds_list) >= n:
                    for i in range(m):
                        cd_list[i] += self.ds_list[-n]['level' + str(i+1)]
                    n += 1
                    if n >= 11:
                        break

                for i in range(m):
                    temp = None
                    if n == 1:
                        temp = cd_list[i]+1
                    else:
                        temp = cd_list[i]/(n-1)+1
                    ad_list.append(temp)

                c = 5
                decay = 0.8
                offset = 0

                for i in range(m):
                    offset += int(mlofi_list[i]*c*pow(decay,i)/ ad_list[i])


                benchmark = quoteprice;
                if(lob['midprice'] != None):
                        benchmark = lob['midprice']
                # print 'midprice is %d' % benchmark


                quoteprice_mlofi = quoteprice + 0.8 * (benchmark + offset - quoteprice)
                if self.job == 'Bid' and quoteprice_mlofi > self.limit:
                    quoteprice_mlofi = self.limit
                if self.job == 'Ask' and quoteprice_mlofi < self.limit:
                    quoteprice_mlofi = self.limit



                if countdown < 0.3 :
                    print "insert"
                    if self.job == 'Bid' and (len(lob['asks']['lob']) >= 1) and lob['asks']['lob'][0][0] < self.limit:
                        quoteprice_mlofi = lob['asks']['lob'][0][0]
                    if self.job == 'Ask' and (len(lob['bids']['lob']) >= 1) and lob['bids']['lob'][0][0] > self.limit:
                        quoteprice_mlofi = lob['bids']['lob'][0][0]

                if self.job == 'Bid' and quoteprice_mlofi < bse_sys_minprice:
                    quoteprice_mlofi = bse_sys_minprice + 1
                if self.job == 'Ask' and quoteprice_mlofi > bse_sys_maxprice:
                    quoteprice_mlofi = bse_sys_maxprice - 1

                return quoteprice_mlofi

            quoteprice_isimple = imbalance_alter(quoteprice, lob,countdown,self.m)

            order = Order(self.tid,
                          self.orders[0].atype,
                          'LIM',
                          quoteprice_isimple,
                          self.orders[0].qty,
                          time, None, -1)
            self.lastquote = order
        return order

    def respond(self, time, lob, trade, verbose):

        if (self.last_lob == None):
            self.last_lob = lob
        else:
            self.calc_es(lob, self.m, verbose)
            self.calc_ds(lob, self.m, verbose)
            self.last_lob = lob;

