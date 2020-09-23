
from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math

bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies


class Trader_IAA_NEW(Trader):

    def __init__(self, ttype, tid, balance, time,m):

        Trader.__init__(self, ttype, tid, balance, time)

        self.limit = None
        self.job = None

        # learning variables
        self.r_shout_change_relative = 0.05
        self.r_shout_change_absolute = 0.05
        self.short_term_learning_rate = random.uniform(0.1, 0.5)
        self.long_term_learning_rate = random.uniform(0.1, 0.5)
        self.moving_average_weight_decay = 0.95  # how fast weight decays with time, lower is quicker, 0.9 in vytelingum
        self.moving_average_window_size = 5
        self.offer_change_rate = 3.0
        self.theta = -2.0
        self.theta_max = 2.0
        self.theta_min = -8.0
        self.marketMax = bse_sys_maxprice

        # Variables to describe the market
        self.previous_transactions = []
        self.moving_average_weights = []
        for i in range(self.moving_average_window_size):
            self.moving_average_weights.append(self.moving_average_weight_decay ** i)
        self.estimated_equilibrium = []
        self.smiths_alpha = []
        self.prev_best_bid_p = None
        self.prev_best_bid_q = None
        self.prev_best_ask_p = None
        self.prev_best_ask_q = None

        # Trading Variables
        self.r_shout = None
        self.buy_target = None
        self.sell_target = None
        self.buy_r = -1.0 * (0.3 * random.random())
        self.sell_r = -1.0 * (0.3 * random.random())

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

    def calcEq(self):  ##clear and correct
        # Slightly modified from paper, it is unclear inpaper
        # N previous transactions * weights / N in vytelingum, swap N denominator for sum of weights to be correct?
        if len(self.previous_transactions) == 0:
            return
        elif len(self.previous_transactions) < self.moving_average_window_size:
            # Not enough transactions
            self.estimated_equilibrium.append(
                float(sum(self.previous_transactions)) / max(len(self.previous_transactions), 1))
        else:
            N_previous_transactions = self.previous_transactions[-self.moving_average_window_size:]
            thing = [N_previous_transactions[i] * self.moving_average_weights[i] for i in
                     range(self.moving_average_window_size)]
            eq = sum(thing) / sum(self.moving_average_weights)
            self.estimated_equilibrium.append(eq)

    def calcAlpha(self):  ##correct. but calcAlpha in snashall's version is incorrect
        alpha = 0.0
        for p in self.previous_transactions:
            alpha += (p - self.estimated_equilibrium[-1]) ** 2
        alpha = math.sqrt(alpha / len(self.previous_transactions))
        self.smiths_alpha.append(alpha / self.estimated_equilibrium[-1])

    def calcTheta(self):  ## clear and correct
        gamma = 2.0  # not sensitive apparently so choose to be whatever
        # necessary for intialisation, div by 0
        if min(self.smiths_alpha) == max(self.smiths_alpha):
            alpha_range = 0.4  # starting value i guess
        else:
            alpha_range = (self.smiths_alpha[-1] - min(self.smiths_alpha)) / (
                    max(self.smiths_alpha) - min(self.smiths_alpha))
        theta_range = self.theta_max - self.theta_min
        desired_theta = self.theta_min + (theta_range) * (1 - alpha_range) * math.exp(gamma * (alpha_range - 1))
        self.theta = self.theta + self.long_term_learning_rate * (desired_theta - self.theta)
        if self.theta > self.theta_max:
            self.theta = self.theta_max
        if self.theta < self.theta_min:
            self.theta = self.theta_min

    def calcRshout(self):  ## unclear in Vytelingum's paper
        p = self.estimated_equilibrium[-1]
        l = self.limit
        theta = self.theta
        if self.job == 'Bid':
            # Currently a buyer
            if l <= p:  # extramarginal!
                self.r_shout = 0.0
            else:  # intramarginal :(
                if self.buy_target > self.estimated_equilibrium[-1]:
                    # r[0,1]
                    self.r_shout = math.log(((self.buy_target - p) * (math.exp(theta) - 1) / (l - p)) + 1) / theta
                else:
                    # r[-1,0]
                    # print 'buy_target: %f , p: %f , theta: %f' %(self.buy_target,p,theta)
                    self.r_shout = math.log((1 - (self.buy_target / p)) * (math.exp(theta) - 1) + 1) / theta
                # self.r_shout = self.buy_r

        if self.job == 'Ask':
            # Currently a seller
            if l >= p:  # extramarginal!
                self.r_shout = 0
            else:  # intramarginal :(
                if self.sell_target > self.estimated_equilibrium[-1]:
                    # r[-1,0]
                    self.r_shout = math.log(
                        (self.sell_target - p) * (math.exp(theta) - 1) / (self.marketMax - p) + 1) / theta
                else:
                    # r[0,1]
                    a = (self.sell_target - l) / (p - l)
                    self.r_shout = (math.log((1 - a) * (math.exp(theta) - 1) + 1)) / theta
                # self.r_shout = self.sell_r

    def calcAgg(self):
        delta = 0
        if self.job == 'Bid':
            # BUYER
            if self.buy_target >= self.previous_transactions[-1]:
                # must be more aggressive
                delta = (1 + self.r_shout_change_relative) * self.r_shout + self.r_shout_change_absolute
            else:
                delta = (1 - self.r_shout_change_relative) * self.r_shout - self.r_shout_change_absolute

            self.buy_r = self.buy_r + self.short_term_learning_rate * (delta - self.buy_r)

        if self.job == 'Ask':
            # SELLER
            if self.sell_target > self.previous_transactions[-1]:
                delta = (1 + self.r_shout_change_relative) * self.r_shout + self.r_shout_change_absolute
            else:
                delta = (1 - self.r_shout_change_relative) * self.r_shout - self.r_shout_change_absolute

            self.sell_r = self.sell_r + self.short_term_learning_rate * (delta - self.sell_r)

    def calcTarget(self):
        if len(self.estimated_equilibrium) > 0:
            p = self.estimated_equilibrium[-1]
            if self.limit == p:
                p = p * 1.000001  # to prevent theta_bar = 0
        elif self.job == 'Bid':
            p = self.limit - self.limit * 0.2  ## Initial guess for eq if no deals yet!!....
        elif self.job == 'Ask':
            p = self.limit + self.limit * 0.2
        l = self.limit
        theta = self.theta
        if self.job == 'Bid':
            # BUYER
            minus_thing = self.buy_r * math.exp(theta * (self.buy_r - 1))

            if l <= p:  # Extramarginal
                if self.buy_r >= 0:
                    self.buy_target = l
                else:
                    self.buy_target = l * (1 - minus_thing)
            else:  # intramarginal
                if self.buy_r >= 0:
                    # theta_ba = (p * math.exp(-theta))/(l-p)-1
                    theta_ba = theta
                    # print 'theta: %f' %(self.theta)
                    # print 'theta_ba: %f '%(theta_ba)
                    # print 'l-p: %f '%(l-p)
                    # print 'self.buy_r :%f' %(self.buy_r)

                    self.buy_target = (l - p) * (1 - (self.buy_r + 1) * math.exp(self.buy_r * theta_ba)) + p
                else:
                    self.buy_target = p * (1 - minus_thing)
            if self.buy_target > l:
                self.buy_target = l
            if self.buy_target < bse_sys_minprice:
                self.buy_target = bse_sys_minprice
            # print 'buy_target = %f'%(self.buy_target)

        if self.job == 'Ask':
            # SELLER

            if l <= p:  # Intramarginal
                if self.buy_r >= 0:
                    self.buy_target = p + (p - l) * self.sell_r * math.exp((self.sell_r - 1) * theta)
                else:
                    theta_ba = math.log((self.marketMax - p) / (p - l)) - theta
                    self.buy_target = p + (self.marketMax - p) * self.sell_r * math.exp((self.sell_r + 1) * theta_ba)
            else:  # Extramarginal
                if self.buy_r >= 0:
                    self.buy_target = l
                else:
                    self.buy_target = l + (self.marketMax - l) * self.sell_r * math.exp((self.sell_r - 1) * theta)
            if self.sell_target < l:
                self.sell_target = l
            if self.sell_target > bse_sys_maxprice:
                self.sell_target = bse_sys_maxprice
            # print 'sell_target = %f'%(self.sell_target)

    def getorder(self, time, countdown, lob, verbose):
        if len(self.orders) < 1:
            self.active = False
            return None
        else:
            self.active = True
            self.limit = self.orders[0].price
            self.job = self.orders[0].atype
            self.calcTarget()

            if self.prev_best_bid_p == None:
                o_bid = 0
            else:
                o_bid = self.prev_best_bid_p
            if self.prev_best_ask_p == None:
                o_ask = self.marketMax
            else:
                o_ask = self.prev_best_ask_p

            if self.job == 'Bid':  # BUYER
                if self.limit <= o_bid:
                    return None
                else:
                    if len(self.previous_transactions) <= 0:  ## has been at least one transaction
                        o_ask_plus = (1 + self.r_shout_change_relative) * o_ask + self.r_shout_change_absolute
                        quoteprice = o_bid + ((min(self.limit, o_ask_plus) - o_bid) / self.offer_change_rate)
                    else:
                        if o_ask <= self.buy_target:
                            quoteprice = o_ask
                        else:
                            quoteprice = o_bid + ((self.buy_target - o_bid) / self.offer_change_rate)
            if self.job == 'Ask':
                if self.limit >= o_ask:
                    return None
                else:
                    if len(self.previous_transactions) <= 0:  ## has been at least one transaction
                        o_bid_minus = (1 - self.r_shout_change_relative) * o_bid - self.r_shout_change_absolute
                        quoteprice = o_ask - ((o_ask - max(self.limit, o_bid_minus)) / self.offer_change_rate)
                    else:
                        if o_bid >= self.sell_target:
                            quoteprice = o_bid
                        else:
                            quoteprice = o_ask - ((o_ask - self.sell_target) / self.offer_change_rate)

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


            order = Order(self.tid,
                          self.orders[0].atype,
                          'LIM',
                          quoteprice_iaa,
                          self.orders[0].qty,
                          time, None, -1)
            self.lastquote = order
        return order

    def respond(self, time, lob, trade, verbose):
        ## Begin nicked from ZIP

        # what, if anything, has happened on the bid LOB? Nicked from ZIP..
        bid_improved = False
        bid_hit = False
        lob_best_bid_p = lob['bids']['bestp']
        lob_best_bid_q = None
        if lob_best_bid_p != None:
            # non-empty bid LOB
            lob_best_bid_q = lob['bids']['lob'][0][1]
            if self.prev_best_bid_p < lob_best_bid_p:
                # best bid has improved
                # NB doesn't check if the improvement was by self
                bid_improved = True
            elif trade != None and ((self.prev_best_bid_p > lob_best_bid_p) or (
                    (self.prev_best_bid_p == lob_best_bid_p) and (self.prev_best_bid_q > lob_best_bid_q))):
                # previous best bid was hit
                bid_hit = True
        elif self.prev_best_bid_p != None:
            # # the bid LOB has been emptied: was it cancelled or hit?
            # last_tape_item = lob['tape'][-1]
            # if last_tape_item['type'] == 'Cancel' :
            #         bid_hit = False
            # else:
            #         bid_hit = True
            # the bid LOB is empty now but was not previously: so was it canceled or lifted?
            if trade != None:
                # a trade has occurred and the previously nonempty ask LOB is now empty
                # so assume best ask was lifted
                bid_hit = True
            else:
                bid_hit = False
        # what, if anything, has happened on the ask LOB?
        ask_improved = False
        ask_lifted = False
        lob_best_ask_p = lob['asks']['bestp']
        lob_best_ask_q = None
        if lob_best_ask_p != None:
            # non-empty ask LOB
            lob_best_ask_q = lob['asks']['lob'][0][1]
            if self.prev_best_ask_p > lob_best_ask_p:
                # best ask has improved -- NB doesn't check if the improvement was by self
                ask_improved = True
            elif trade != None and ((self.prev_best_ask_p < lob_best_ask_p) or (
                    (self.prev_best_ask_p == lob_best_ask_p) and (self.prev_best_ask_q > lob_best_ask_q))):
                # trade happened and best ask price has got worse, or stayed same but quantity reduced -- assume previous best ask was lifted
                ask_lifted = True
        elif self.prev_best_ask_p != None:
            # the ask LOB is empty now but was not previously: canceled or lifted?
            # last_tape_item = lob['tape'][-1]
            # if last_tape_item['type'] == 'Cancel' :
            #         ask_lifted = False
            # else:
            #         ask_lifted = True
            # the ask LOB is empty now but was not previously: so was it canceled or lifted?
            if trade != None:
                # a trade has occurred and the previously nonempty ask LOB is now empty
                # so assume best ask was lifted
                ask_lifted = True
            else:
                ask_lifted = False

        self.prev_best_bid_p = lob_best_bid_p
        self.prev_best_bid_q = lob_best_bid_q
        self.prev_best_ask_p = lob_best_ask_p
        self.prev_best_ask_q = lob_best_ask_q

        deal = bid_hit or ask_lifted

        ## End nicked from ZIP
        if (self.last_lob == None):
            self.last_lob = lob
        else:
            self.calc_es(lob, self.m, verbose)
            self.calc_ds(lob, self.m, verbose)
            self.calc_bids_volume(lob, self.m, verbose)
            self.calc_asks_volume(lob, self.m, verbose)
            self.last_lob = lob;

        if deal:
            self.previous_transactions.append(trade['price'])
            if self.sell_target == None:
                self.sell_target = trade['price']
            if self.buy_target == None:
                self.buy_target = trade['price']

            self.calcEq()
            self.calcAlpha()
            self.calcTheta()
            self.calcRshout()
            self.calcAgg()
            self.calcTarget()
            # print 'sell: ', self.sell_target, 'buy: ', self.buy_target, 'limit:', self.limit, 'eq: ',  self.estimated_equilibrium[-1], 'sell_r: ', self.sell_r, 'buy_r: ', self.buy_r, '\n'
