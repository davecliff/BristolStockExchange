<i>NB: in Q4 of 2022, a decade afterBSE was first launched, we'll be making BSE2 available in a separate repo. BSE2 is a major refactoring and extension of the original BSE. This, the original BSE repo, will be retained for legacy and reference, and because the code is old and stable and simple; but for advanced usage BSE2 should be the preferred choice once it is available.</i>

BSE, The Bristol Stock Exchange, is a simple minimal simulation of a limit-order-book financial exchange, developed for teaching. The aim is to let students explore writing automated trading strategies that deal with "Level 2" market data.

It is written in Python, is single-threaded and all in one file for ease of use by novices. The file BSEguide.pdf explains much of what is going on and includes an example programming assignment. The Wiki here on the BSE GitHub site holds a copy of the BSEguide text: it may be that the Wiki text is more up to date than the PDF file. 

The code in BSE is based on a large number of simplifying assumptions, chief of which is absolute-zero latency: if a trader issues a new quote, that gets processed by the exchange and all other traders can react to it, in zero time (i.e., before any other quote is issued). 

Nevertheless, because the BSE system is stochastic it can also be used to introduce issues in the design of experiments and analysis of empirical data.

Real exchanges are much much more complicated than this. 

If you use BSE in your work, please link back to this GitHub page for BSE so that people know where to find the original Python source-code: https://github.com/davecliff/BristolStockExchange, and please also cite the peer-reviewed paper that describes BSE:
 
Cliff, D. (2018). BSE: A Minimal Simulation of a Limit-Order-Book Stock Exchange. In M. Affenzeller, et al. (Eds.), Proceedings 30th European Modeling and Simulation Symposium (EMSS 2018), pp. 194-203. DIME University of Genoa.
 
Which you can download from here:
https://research-information.bris.ac.uk/ws/portalfiles/portal/167944812/Cliff_i3M_CRC_formatted_repository.pdf

or here:
https://arxiv.org/abs/1809.06027


The code is open-sourced via the MIT Licence: see the LICENSE file for full text. 
(copied from http://opensource.org/licenses/mit-license.php)

Last update: Dave Cliff, March 23rd 2021.
