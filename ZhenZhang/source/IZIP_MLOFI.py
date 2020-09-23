
from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math

bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies

class Trader_IZIP_MLOFI(Trader):

    # ZIP init key param-values are those used in Cliff's 1997 original HP Labs tech report
    # NB this implementation keeps separate margin values for buying & selling,
    #    so a single trader can both buy AND sell
    #    -- in the original, traders were either buyers OR sellers

    def __init__(self, ttype, tid, balance, time, m):
        Trader.__init__(self, ttype, tid, balance, time)
        m_fix = 0.05
        m_var = 0.05
        self.job = None  # this is 'Bid' or 'Ask' depending on customer order
        self.active = False  # gets switched to True while actively working an order
        self.prev_change = 0  # this was called last_d in Cliff'97
        self.beta = 0.1 + 0.2 * random.random()  # learning rate
        self.momntm = 0.3 * random.random()  # momentum
        self.ca = 0.10  # self.ca & .cr were hard-coded in '97 but parameterised later
        self.cr = 0.10
        self.margin = None  # this was called profit in Cliff'97
        self.margin_buy = -1.0 * (m_fix + m_var * random.random())
        self.margin_sell = m_fix + m_var * random.random()
        self.price = None
        self.limit = None
        # memory of best price & quantity of best bid and ask, on LOB on previous update
        self.prev_best_bid_p = None
        self.prev_best_bid_q = None
        self.prev_best_ask_p = None
        self.prev_best_ask_q = None
        # memory of worst prices from customer orders received so far
        self.worst_bidprice = None
        self.worst_askprice = None


        # variable for MLOFI
        self.last_lob = None;
        self.es_list = [];
        self.ds_list = [];

        #variable for ratio
        self.bids_volume_list = []
        self.asks_volume_list = []

        #variable
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



    def __str__(self):
        s = '%s, job=, %s, ' % (self.tid, self.job)
        if self.active == True:
            s = s + 'actv=,T, '
        else:
            s = s + 'actv=,F, '
        if self.margin == None:
            s = s + 'mrgn=,N,   '
        else:
            s = s + 'mrgn=,%5.2f, ' % self.margin
        s = s + 'lmt=,%s, price=,%s, bestbid=,%s,@,%s, bestask=,%s,@,%s, wrstbid=,%s, wrstask=,%s' % \
            (self.limit, self.price, self.prev_best_bid_q, self.prev_best_bid_p, self.prev_best_ask_q,
             self.prev_best_ask_p, self.worst_bidprice, self.worst_askprice)
        return (s)

    def getorder(self, time, countdown, lob, verbose):

        if verbose: print('ZIP getorder(): LOB=%s' % lob)

        # random coefficient, multiplier on trader's own estimate of worst possible bid/ask prices
        # currently in arbitrarily chosen range [2, 5]
        worst_coeff = 2 + (3 * random.random())

        if len(self.orders) < 1:
            self.active = False
            order = None
        else:
            self.active = True
            self.limit = self.orders[0].price
            self.job = self.orders[0].atype
            if self.job == 'Bid':
                # currently a buyer (working a bid order)
                self.margin = self.margin_buy
                # what is the worst bid price on the LOB right now?
                if len(lob['bids']['lob']) > 0:
                    # take price of final entry on LOB
                    worst_bid = lob['bids']['lob'][-1][0]
                else:
                    # local pessimistic estimate of the worst bid price (own version of stub quote)
                    worst_bid = max(1, int(self.limit / worst_coeff))
                if self.worst_bidprice == None:
                    self.worst_bidprice = worst_bid
                elif self.worst_bidprice > worst_bid:
                    self.worst_bidprice = worst_bid
            else:
                # currently a seller (working a sell order)
                self.margin = self.margin_sell
                # what is the worst ask price on the LOB right now?
                if len(lob['asks']['lob']) > 0:
                    # take price of final entry on LOB
                    worst_ask = lob['asks']['lob'][-1][0]
                else:
                    # local pessimistic estimate of the worst ask price (own version of stub quote)
                    worst_ask = int(self.limit * worst_coeff)
                if self.worst_askprice == None:
                    self.worst_askprice = worst_ask
                elif self.worst_askprice < worst_ask:
                    self.worst_askprice = worst_ask

            quoteprice = int(self.limit * (1 + self.margin))

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

                c = 10
                decay = 1
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
                        quoteprice_iaa = lob['asks']['lob'][0][0]+1
                    if self.job == 'Ask' and (len(lob['bids']['lob']) >= 1) and lob['bids']['lob'][0][0] > self.limit:
                        quoteprice_iaa = lob['bids']['lob'][0][0]-1


                if self.job == 'Bid' and quoteprice_iaa < bse_sys_minprice:
                    quoteprice_iaa = bse_sys_minprice + 1
                if self.job == 'Ask' and quoteprice_iaa > bse_sys_maxprice:
                    quoteprice_iaa = bse_sys_maxprice - 1

                return quoteprice_iaa

            # print "before"
            # print quoteprice
            # if(self.is_imbalance_significant(self.m,0.6)):
            #     print "abvious"
            #     quoteprice_izip = imbalance_alter(quoteprice, lob, countdown, self.m)
            # else:
            #     print "not abvious"
            #     quoteprice_izip = quoteprice
            quoteprice_izip = imbalance_alter(quoteprice, lob, countdown, self.m)
            # print "after"
            # print quoteprice_izip



            self.price = quoteprice_izip

            order = Order(self.tid, self.job, "LIM", quoteprice_izip, self.orders[0].qty, time, None, -1)
            self.lastquote = order

        return order

    # update margin on basis of what happened in market
    def respond(self, time, lob, trade, verbose):
        # ZIP trader responds to market events, altering its margin
        # does this whether it currently has an order to work or not


        if (self.last_lob == None):
            self.last_lob = lob
        else:
            self.calc_es(lob, self.m, verbose)
            self.calc_ds(lob, self.m, verbose)
            self.calc_bids_volume(lob, self.m, verbose)
            self.calc_asks_volume(lob, self.m, verbose)
            self.last_lob = lob;

        def target_up(price):
            # generate a higher target price by randomly perturbing given price
            ptrb_abs = self.ca * random.random()  # absolute shift
            ptrb_rel = price * (1.0 + (self.cr * random.random()))  # relative shift
            target = int(round(ptrb_rel + ptrb_abs, 0))
            if target == price: target = price + 1  # enforce minimal difference
            # print('TargetUp: %d %d\n' % (price, target))
            return (target)

        def target_down(price):
            # generate a lower target price by randomly perturbing given price
            ptrb_abs = self.ca * random.random()  # absolute shift
            ptrb_rel = price * (1.0 - (self.cr * random.random()))  # relative shift
            target = int(round(ptrb_rel - ptrb_abs, 0))
            if target == price: target = price - 1  # enforce minimal difference
            # print('TargetDn: %d %d\n' % (price,target))
            return (target)

        def microshade(microprice, price):
            # shade in the direction of the microprice
            microweight = 0
            if microprice != None:
                shaded = ((microweight * microprice) + ((1 - microweight) * price))
            else:
                shaded = price
            # print('Microshade: micro=%s price=%s shaded=%s' % (microprice, price, shaded))
            return (shaded)

        def willing_to_trade(price):
            # am I willing to trade at this price?
            willing = False
            if self.job == 'Bid' and self.active and self.price >= price:
                willing = True
            if self.job == 'Ask' and self.active and self.price <= price:
                willing = True
            return willing

        def profit_alter(*argv):
            # this has variable number of parameters
            # if passed a single numeric value, that's the target price
            # if passed three numeric values, that's the price, beta (learning rate), and momentum
            if len(argv) == 1:
                price = argv[0]
                beta = self.beta
                momntm = self.momntm
            elif len(argv) == 3:
                price = argv[0]
                beta = argv[1]
                momntm = argv[2]
            else:
                sys.stdout.flush()
                sys.exit('Fail: ZIP profit_alter given wrong number of parameters')

            # print('profit_alter: price=%s beta=%s momntm=%s' % (price, beta, momntm))
            oldprice = self.price
            diff = price - oldprice
            change = ((1.0 - self.momntm) * (self.beta * diff)) + (self.momntm * self.prev_change)
            self.prev_change = change
            newmargin = ((self.price + change) / self.limit) - 1.0

            if self.job == 'Bid':
                margin = min(newmargin, 0)
                self.margin_buy = margin
                self.margin = margin
            else:
                margin = max(0, newmargin)
                self.margin_sell = margin
                self.margin = margin

            # set the price from limit and profit-margin
            self.price = int(round(self.limit * (1.0 + self.margin), 0))
            # print('old=%d diff=%d change=%d lim=%d price = %d\n' % (oldprice, diff, change, self.limit, self.price))

        if verbose and trade != None: print('respond() [ZIP] time=%s tid=%s, trade=%s LOB[bids]=%s LOB[asks]=%s' %
                                            (time, self.tid, trade, lob["bids"], lob["asks"]))

        # what, if anything, has happened on the bid LOB?

        # if trade != None: print('ZIP respond() trade=%s' % trade)

        bid_improved = False
        bid_hit = False

        if len(lob['bids']['lob']) > 0:
            lob_best_bid_p = lob['bids']['lob'][0][0]
        else:
            lob_best_bid_p = None

        lob_best_bid_q = None  # default assumption

        if lob_best_bid_p != None:
            # non-empty bid LOB

            if self.prev_best_bid_p > lob_best_bid_p:
                best_bid_p_decreased = True
            else:
                best_bid_p_decreased = False

            if (self.prev_best_bid_p == lob_best_bid_p) and (self.prev_best_bid_q > lob_best_bid_q):
                same_p_smaller_q = True
            else:
                same_p_smaller_q = False

            lob_best_bid_q = lob['bids']['lob'][0][1]

            if self.prev_best_bid_p < lob_best_bid_p:
                # best bid has improved
                # NB doesn't check if the improvement was by self
                bid_improved = True
            elif trade != None and (best_bid_p_decreased or same_p_smaller_q):
                # there WAS a trade and either...
                # ... (best bid price has gone DOWN) or (best bid price is same but quantity at that price has gone DOWN)
                # then assume previous best bid was hit
                bid_hit = True

        elif self.prev_best_bid_p != None:
            # the bid LOB is empty now but was not previously: so was it canceled or lifted?
            if trade != None:
                # a trade has occurred and the previously nonempty ask LOB is now empty
                # so assume best ask was lifted
                bid_hit = True
            else:
                bid_hit = False

        if verbose: print("LOB[bids]=%s bid_improved=%s bid_hit=%s" % (lob['bids'], bid_improved, bid_hit))

        # what, if anything, has happened on the ask LOB?

        ask_improved = False
        ask_lifted = False

        if len(lob['asks']['lob']) > 0:
            lob_best_ask_p = lob['asks']['lob'][0][0]
        else:
            lob_best_ask_p = None

        lob_best_ask_q = None

        if lob_best_ask_p != None:
            # non-empty ask LOB

            if self.prev_best_ask_p < lob_best_ask_p:
                best_ask_p_increased = True
            else:
                best_ask_p_increased = False

            if (self.prev_best_ask_p == lob_best_ask_p) and (self.prev_best_ask_q > lob_best_ask_q):
                same_p_smaller_q = True
            else:
                same_p_smaller_q = False

            lob_best_ask_q = lob['asks']['lob'][0][1]
            if self.prev_best_ask_p > lob_best_ask_p:
                # best ask has improved -- NB doesn't check if the improvement was by self
                ask_improved = True
            elif trade != None and (best_ask_p_increased or same_p_smaller_q):
                # trade happened and best ask price has got worse, or stayed same but quantity reduced -- assume previous best ask was lifted
                ask_lifted = True

        elif self.prev_best_ask_p != None:
            # the ask LOB is empty now but was not previously: so was it canceled or lifted?
            if trade != None:
                # a trade has occurred and the previously nonempty ask LOB is now empty
                # so assume best ask was lifted
                ask_lifted = True
            else:
                ask_lifted = False

        if verbose: print("LOB[asks]=%s ask_improved=%s ask_lifted=%s" % (lob['asks'], ask_improved, ask_lifted))

        if verbose and (bid_improved or bid_hit or ask_improved or ask_lifted):
            print('ZIP respond() B_improved=%s; B_hit=%s A_improved=%s, A_lifted=%s' % (
            bid_improved, bid_hit, ask_improved, ask_lifted))
            print('Trade=%s\n' % trade)

        # we want to know: did a deal just happen?
        # if not, did the most recent bid

        deal = bid_hit or ask_lifted

        # previously...
        # when raising margin, tradeprice = trade['price'], targetprice = f(tradeprice) &
        # i.e. target price will be calculated relative to price of most recent transaction
        # and when lowering margin, targetprice = f(best_price_on_counterparty_side_of_LOB) or
        # or if LOB empty then targetprice = f(worst possible counterparty quote) <-- a system constant

        # new in this version:
        # take account of LOB's microprice if it is defined (if not, use trade['price'] as before)

        midp = lob['midprice']
        microp = lob['microprice']

        # KLUDGE for TESTING
        if time > 79: microp = 145

        if microp != None and midp != None:
            imbalance = microp - midp
        else:
            imbalance = 0  # uses zero instead of None because a zero imbalance reverts ZIP to original form

        target_price = None  # default assumption

        # print('self.job=%s' % self.job)

        if self.job == 'Ask':
            # seller
            if deal:
                if verbose: print ('trade', trade)
                tradeprice = trade['price']  # price of most recent transaction
                # print('tradeprice=%s lob[microprice]=%s' % (tradeprice, lob['microprice']))
                # shadetrade = microshade(lob['microprice'], tradeprice)
                # refprice = shadetrade
                refprice = tradeprice

                if self.price <= tradeprice:
                    # could sell for more? raise margin
                    target_price = target_up(refprice)
                    profit_alter(target_price)
                elif ask_lifted and self.active and not willing_to_trade(tradeprice):
                    # previous best ask was hit,
                    # but this trader wouldn't have got the deal cos price to high,
                    # and still working a customer order, so reduce margin
                    target_price = target_down(refprice)
                    profit_alter(target_price)
            else:
                # no deal: aim for a target price higher than best bid
                # print('lob_best_bid_p=%s lob[microprice]=%s' % (lob_best_bid_p, lob['microprice']))
                # refprice = microshade(lob['microprice'], lob_best_bid_p)
                refprice = lob_best_bid_p

                if ask_improved and self.price > lob_best_bid_p:
                    if lob_best_bid_p != None:
                        target_price = target_up(lob_best_bid_p)
                    else:
                        if self.worst_askprice != None:
                            target_price = self.worst_askprice
                            print('worst_askprice = %s' % self.worst_askprice)
                            target_price = None  # todo: does this stop the price-spikes?
                        else:
                            target_price = None
                        # target_price = lob['asks']['worstp']  # stub quote
                    if target_price != None:
                        print('PA1: tp=%s' % target_price)
                        profit_alter(target_price)

        if self.job == 'Bid':
            # buyer
            if deal:
                tradeprice = trade['price']
                # shadetrade = microshade(lob['microprice'], tradeprice)
                # refprice = shadetrade
                refprice = tradeprice

                if lob['microprice'] != None and lob['midprice'] != None:
                    delta = lob['microprice'] - lob['midprice']
                    # refprice = refprice + delta

                if self.price >= tradeprice:
                    # could buy for less? raise margin (i.e. cut the price)
                    target_price = target_down(refprice)
                    profit_alter(target_price)
                elif bid_hit and self.active and not willing_to_trade(tradeprice):
                    # wouldn't have got this deal, and still working a customer order,
                    # so reduce margin
                    target_price = target_up(refprice)
                    profit_alter(target_price)
            else:
                # no deal: aim for target price lower than best ask
                refprice = microshade(lob['microprice'], lob_best_ask_p)
                if bid_improved and self.price < lob_best_ask_p:
                    if lob_best_ask_p != None:
                        target_price = target_down(lob_best_ask_p)
                    else:
                        if self.worst_bidprice != None:
                            target_price = self.worst_bidprice
                            target_price = None
                        else:
                            target_price = None
                        # target_price = lob['bids']['worstp']  # stub quote
                    if target_price != None:
                        # print('PA2: tp=%s' % target_price)
                        profit_alter(target_price)

        # print('time,%f,>>>,microprice,%s,>>>,target_price,%s' % (time, lob['microprice'], target_price))

        # remember the best LOB data ready for next response
        self.prev_best_bid_p = lob_best_bid_p
        self.prev_best_bid_q = lob_best_bid_q
        self.prev_best_ask_p = lob_best_ask_p
        self.prev_best_ask_q = lob_best_ask_q

##########################---trader-types have all been defined now--################