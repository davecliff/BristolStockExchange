<i>NB: in Q1 of 2021, more than eight years since BSE was first launched, we'll be making BSE2 available in a separate repo. BSE2 is a major refactoring and extension of the original BSE. This, the original BSE repo, will be retained for legacy and reference, but BSE2 should be used in future.</i>

BSE, The Bristol Stock Exchange, is a simple minimal simulation of a limit-order-book financial exchange, developed for teaching. The aim is to let students explore writing automated trading strategies that deal with "Level 2" market data.

It is written in Python, is single-threaded and all in one file for ease of use by novices. The file BSEguide.pdf explains much of what is going on and includes an example programming assignment. The Wiki here on the BSE GitHub site holds a copy of the BSEguide text: it may be that the Wiki text is more up to date than the PDF file. 

The code in BSE is based on a large number of simplifying assumptions, chief of which is absolute-zero latency: if a trader issues a new quote, that gets processed by the exchange and all other traders can react to it, in zero time (i.e., before any other quote is issued). 

Nevertheless, because the BSE system is stochastic it can also be used to introduce issues in the design of experiments and analysis of empirical data.

Real exchanges are much much more complicated than this. 

The code is open-sourced via the MIT Licence: see the LICENSE file for full text. 
(copied from http://opensource.org/licenses/mit-license.php)

Last update: Dave Cliff, October 25th 2012.
