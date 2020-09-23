from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math

bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies

class Trader_Simple_MLOFI(Trader):

    def __init__(self, ttype, tid, balance, time):

        Trader.__init__(self, ttype, tid, balance, time)

        self.limit = None
        self.job = None


        # variable for MLOFI
        self.last_lob = None;
        self.list_OFI = [];
        self.list_D = [];

    def cal_level_n_e(self, current_lob, n):
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

    def cal_e(self, time, lob, trade, verbose):

        level_1 = self.cal_level_n_e(lob, 1)
        level_2 = self.cal_level_n_e(lob, 2)
        level_3 = self.cal_level_n_e(lob, 3)
        e = {
            'level1': level_1,
            'level2': level_2,
            'level3': level_3,
        }
        # print 'ofi is:'
        # print str(e)
        self.list_OFI.append(e)

    def cal_depth(self, lob):
        level_1 = self.cal_depth_n(lob, 1)
        level_2 = self.cal_depth_n(lob, 2)
        level_3 = self.cal_depth_n(lob, 3)
        d = {
            'level1': level_1,
            'level2': level_2,
            'level3': level_3,
        }
        # print 'depth is:'
        # print str(d)
        self.list_D.append(d);

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
                if lob['bids']['n'] > 0:
                    quoteprice = lob['bids']['bestp']
                    if quoteprice > self.limit:
                        quoteprice = self.limit
                else:
                    quoteprice = self.limit
            else:
                if lob['asks']['n'] > 0:
                    quoteprice = lob['asks']['bestp']
                    if quoteprice < self.limit:
                        quoteprice = self.limit
                else:
                    quoteprice = self.limit
            def imbalance_alter(quoteprice, lob):


















                level_1_ofi_cul = 0
                level_2_ofi_cul = 0
                level_3_ofi_cul = 0

                n = 1
                while (len(self.list_OFI) >= n):
                    level_1_ofi_cul = level_1_ofi_cul + self.list_OFI[-n]['level1']
                    level_2_ofi_cul = level_2_ofi_cul + self.list_OFI[-n]['level2']
                    level_3_ofi_cul = level_3_ofi_cul + self.list_OFI[-n]['level3']
                    n = n + 1
                    if (n >= 6): break

                level_1_depth_cul = 0;
                level_2_depth_cul = 0;
                level_3_depth_cul = 0;

                m = 1
                while (len(self.list_D) >= m):

                    level_1_depth_cul = level_1_depth_cul + self.list_D[-m]['level1']
                    level_2_depth_cul = level_2_depth_cul + self.list_D[-m]['level2']
                    level_3_depth_cul = level_3_depth_cul + self.list_D[-m]['level3']
                    m = m + 1
                    if (m >= 4): break

                # if(level_1_depth_cul==0): level_1_depth_cul = 10000
                # if(level_2_depth_cul==0): level_2_depth_cul = 10000
                # if(level_3_depth_cul==0): level_3_depth_cul = 10000
                if m == 1:
                    level_1_depth_averge = level_1_depth_cul + 1
                    level_2_depth_averge = level_2_depth_cul + 1
                    level_3_depth_averge = level_3_depth_cul + 1

                else:
                    level_1_depth_averge = level_1_depth_cul / (m - 1) + 1
                    level_2_depth_averge = level_2_depth_cul / (m - 1) + 1
                    level_3_depth_averge = level_3_depth_cul / (m - 1) + 1
                c = 0.5
                decay = 0.8

                # print 'level_1_depth_averge is %s'%level_1_depth_averge
                # print 'level_2_depth_averge is %s'%level_2_depth_averge
                # print 'level_3_depth_averge is %s'%level_3_depth_averge
                offset = level_1_ofi_cul * c / level_1_depth_averge + decay * level_2_ofi_cul * c / level_2_depth_averge + decay * decay * level_3_ofi_cul * c / level_3_depth_averge

                # quoteprice_iaa = (quoteprice_aa+offset)*0.9 + 0.1*quoteprice_aa
                benchmark = quoteprice;
                if(lob['midprice'] != None):
                        benchmark = lob['midprice']
                        # print 'midprice is %d' % benchmark
                # print 'benchmark = %d' % benchmark
                quoteprice_isimple = benchmark + offset
                if self.job == 'Bid' and quoteprice_isimple > self.limit:
                    quoteprice_isimple = self.limit
                if self.job == 'Ask' and quoteprice_isimple < self.limit:
                    quoteprice_isimple = self.limit

                # print 'IAA_MLOFI original quotaprice: %d' % (quoteprice)
                # print 'offset is %d'%offset
                # print 'level1 ofi is %d'%level_1_ofi_cul
                # print 'level2 ofi is %d'%level_2_ofi_cul
                # print 'level3 ofi is %d'%level_3_ofi_cul
                # print 'level1 depth is %d'%level_1_depth_averge
                # print 'level2 depth is %d'%level_2_depth_averge
                # print 'level3 depth is %d'%level_3_depth_averge
                # print 'offset is %d'%offset
                # print 'IAA_MLOFI final quotaprice: %d' % (quoteprice_isimple)
                # print 'IAAB_MLOFI JOB IS %s' % self.job
                return quoteprice_isimple

            quoteprice_isimple = imbalance_alter(quoteprice, lob)

            order = Order(self.tid,
                          self.orders[0].atype,
                          'LIM',
                          quoteprice_isimple,
                          self.orders[0].qty,
                          time, None, -1)
            self.lastquote = order
        return order

    def respond(self, time, lob, trade, verbose):

        ## End nicked from ZIP
        if (self.last_lob == None):
            self.last_lob = lob
        else:
            # print ''
            # print ''
            # print 'pre lob'
            # print 'bid anon:'
            # print self.last_lob['bids']['lob']
            # print 'ask anon:'
            # print self.last_lob['asks']['lob']
            # print 'current lob'
            # print 'bid anon:'
            # print lob['bids']['lob']
            # print 'ask anon:'
            # print lob['asks']['lob']

            self.cal_e(time, lob, trade, verbose)
            self.cal_depth(lob);
            self.last_lob = lob;


