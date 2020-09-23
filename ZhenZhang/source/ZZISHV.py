
from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math
bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies


class Trader_ZZISHV(Trader):

    def __init__(self, ttype, tid, balance, time,m):
        Trader.__init__(self, ttype, tid, balance, time)
        self.limit = None
        self.job = None

        # variable for MLOFI
        self.last_lob = None;
        self.es_list = [];
        self.ds_list = [];

        #variable for ratio
        self.bids_volume_list = []
        self.asks_volume_list = []

        # m
        self.m = m;



    def is_imbalance_significant(self, m,threshold):
        cb_list = [0 for i in range(m)]
        ab_list = []

        ca_list = [0 for i in range(m)]
        aa_list = []

        n = 1

        while len(self.bids_volume_list) >= n and len(self.asks_volume_list) >= n:
            for i in range(m):
                cb_list[i] += self.bids_volume_list[-n]['level' + str(i + 1)]
                ca_list[i] += self.asks_volume_list[-n]['level' + str(i + 1)]
            n += 1
            if n >= 11:
                break


        for i in range(m):
            temp1 = None
            temp2 = None
            if n == 1:
                temp1 = cb_list[i] + 1
                temp2 = ca_list[i] + 1
            else:
                temp1 = cb_list[i] / (n - 1) + 1
                temp2 = ca_list[i] / (n - 1) + 1
            ab_list.append(temp1)
            aa_list.append(temp2)

        v_bid = 0;
        v_ask = 0;
        for i in range(m):
            v_bid += math.exp(-0.5*i)*ab_list[i];
            v_ask += math.exp(-0.5*i)*aa_list[i];
        ratio = (v_bid-v_ask)/(v_bid+v_ask);

        # print self.bids_volume_list
        # print self.asks_volume_list
        # print ratio

        if(ratio>threshold or ratio<-threshold):
            return True
        else:
            return False





    def calc_bids_volume(self, lob, m, verbose):
        new_b = {}

        for i in range(1, m + 1):
            new_b['level' + str(i)] = self.cal_bids_n(lob, i)

        self.bids_volume_list.append(new_b)

    def cal_bids_n(self, lob, n):

        if (len(lob['bids']['lob']) < n):
            r_n = 0
        else:
            r_n = lob['bids']['lob'][n - 1][1]

        return r_n

    def calc_asks_volume(self, lob, m, verbose):
        new_a = {}

        for i in range(1, m + 1):
            new_a['level' + str(i)] = self.cal_asks_n(lob, i);

        self.asks_volume_list.append(new_a)

    def cal_asks_n(self, lob, n):

        if (len(lob['asks']['lob']) < n):
            q_n = 0
        else:
            q_n = lob['asks']['lob'][n - 1][1]
        return q_n

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

    def respond(self, time, lob, trade, verbose):
        if (self.last_lob == None):
            self.last_lob = lob
        else:
            self.calc_es(lob, self.m, verbose)
            self.calc_ds(lob, self.m, verbose)
            self.calc_bids_volume(lob, self.m, verbose)
            self.calc_asks_volume(lob, self.m, verbose)
            self.last_lob = lob


    def getorder(self, time, countdown, lob, verbose):

        if verbose: print("ISHV getorder:")

        shave_c = 2 # c in the y=mx+c linear mapping from imbalance to shave amount
        shave_m = 1 # m in the y=mx+c

        if len(self.orders) < 1:
            order = None
        else:
            if verbose: print(" self.orders[0]=%s" % str(self.orders[0]))
            self.limit = self.orders[0].price
            self.job = self.orders[0].atype

            otype = self.orders[0].atype
            ostyle = self.orders[0].astyle

            microp = lob['microprice']
            midp = lob['midprice']

            if otype == 'Bid':
                if len(lob['bids']['lob']) > 0:
                    quoteprice = lob['bids']['bestp']
                    if quoteprice > self.limit :
                        quoteprice = self.limit
                else:
                    quoteprice = 1  # KLUDGE -- come back to fix todo
            else:

                if len(lob['asks']['lob']) > 0:
                    quoteprice = lob['asks']['bestp']
                    if quoteprice < self.limit:
                        quoteprice = self.limit
                else:
                    quoteprice = 200  # KLUDGE -- come back to fix todo




            def imbalance_alter(quoteprice_aa, lob, countdown, m):

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


                benchmark = quoteprice_aa;
                if(lob['midprice'] != None):
                        benchmark = lob['midprice']
                # print 'midprice is %d' % benchmark

                quoteprice_iaa = quoteprice_aa + 0.8 * (benchmark + offset - quoteprice_aa)
                if self.job == 'Bid' and quoteprice_iaa > self.limit:
                    quoteprice_iaa = self.limit
                if self.job == 'Ask' and quoteprice_iaa < self.limit:
                    quoteprice_iaa = self.limit

                if countdown < 0.3 :
                    print "insert"
                    if self.job == 'Bid' and (len(lob['asks']['lob']) >= 1) and lob['asks']['lob'][0][0] < self.limit:
                        quoteprice_iaa = lob['asks']['lob'][0][0]
                    if self.job == 'Ask' and (len(lob['bids']['lob']) >= 1) and lob['bids']['lob'][0][0] > self.limit:
                        quoteprice_iaa = lob['bids']['lob'][0][0]

                return quoteprice_iaa

            if(self.is_imbalance_significant(self.m,0.6)):
                # print "abvious"
                quoteprice_iaa = imbalance_alter(quoteprice, lob, countdown, self.m)

            else:
                # print "not abvious"
                quoteprice_iaa = quoteprice



            order = Order(self.tid, otype, ostyle, quoteprice_iaa, self.orders[0].qty, time, None, verbose)
            self.lastquote = order
        return order

