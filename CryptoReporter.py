from CryptoParams import *
import CryptoLib as cl
from joblib import Parallel, delayed
import pandas as pd
import numpy as np
import datetime
import time
import termcolor
import sys

###########
# Functions
###########
def bnGetPayments(bn, ccy, isBNT=False):
  if isBNT:
    df = pd.DataFrame(bn.fapiPublic_get_fundingrate({'symbol': ccy + 'USDT', 'startTime': getYest() * 1000}))
  else:
    df = pd.DataFrame(bn.dapiPublic_get_fundingrate({'symbol': ccy + 'USD_PERP', 'startTime': getYest() * 1000}))
  cl.dfSetFloat(df, 'fundingRate')
  df['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in df['fundingTime']]
  df = df.set_index('date').sort_index()
  return df

def bnGetIncomes(bn, validCcys, spotDict, isBNT=False):
  if isBNT:
    df = pd.DataFrame(bn.fapiPrivate_get_income({'incomeType': 'FUNDING_FEE', 'startTime': getYest() * 1000})).set_index('symbol')
  else:
    df = pd.DataFrame(bn.dapiPrivate_get_income({'incomeType': 'FUNDING_FEE', 'startTime': getYest() * 1000})).set_index('symbol')
  cl.dfSetFloat(df, 'income')
  suffix = 'USDT' if isBNT else 'USD_PERP'
  df = df.loc[[z + suffix for z in validCcys]]
  for ccy in validCcys:
    ccy2 = ccy + suffix
    fx = spotDict['USDT'] if isBNT else spotDict[ccy]
    df.loc[ccy2, 'incomeUSD'] = df.loc[ccy2, 'income'] * fx
  df['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in df['time']]
  df = df.set_index('date').sort_index()
  oneDayIncome = df['incomeUSD'].sum()
  prevIncome = df[df.index > df.index[-1] - pd.DateOffset(minutes=10)]['incomeUSD'].sum()
  return oneDayIncome, prevIncome

def getNAVStr(name, nav):
  return name + ': $' + str(round(nav/1000)) + 'K'

def getYest():
  return int((datetime.datetime.timestamp(datetime.datetime.now() - pd.DateOffset(days=1))))

def krPrintAll(krCores,nav):
  # Incomes
  zList = []
  prefixList = []
  for krCore in krCores:
    zList.append('$' + str(round(krCore.oneDayIncome)) + ' (' + str(round(krCore.oneDayAnnRet * 100)) + '% p.a.)')
    prefixList.append('KR' + str(krCore.n))
  print(termcolor.colored(('/'.join(prefixList) + ' 24h rollover fees: ').rjust(41) + ' / '.join(zList), 'blue'))
  #####
  # Borrows
  for krCore in krCores:
    krCore.krPrintBorrow(nav)
  #####
  # Liq
  zList = []
  prefixList = []
  for krCore in krCores:
    zList.append('never' if (krCore.liqBTC <= 0 or krCore.liqBTC > 10) else str(round(krCore.liqBTC * 100)) + '%')
    prefixList.append('KR' + str(krCore.n))
  print(termcolor.colored(('/'.join(prefixList) + ' liquidation (BTC): ').rjust(41) + '/'.join(zList) + ' (of spot)', 'red'))
  print()

def printAllDual(core1, core2):
  if core1.exch == 'dummy' and core2.exch == 'dummy': return
  if core1.exch == 'dummy':
    core2.printAll()
  elif core2.exch == 'dummy':
    core1.printAll()
  else:
    n=120
    print(core1.incomesStr.ljust(n+9) + core2.incomesStr)
    for ccy in sorted(set(core1.validCcys).intersection(core2.validCcys)):
      print(core1.fundingStrDict[ccy].ljust(n) + core2.fundingStrDict[ccy])
    for ccy in sorted(np.setdiff1d(core1.validCcys, core2.validCcys)):  # In core1 but not core2
      print(core1.fundingStrDict[ccy])
    for ccy in sorted(np.setdiff1d(core2.validCcys, core1.validCcys)):  # In core2 but not core1
      print(''.ljust(n) + core2.fundingStrDict[ccy])
    print(core1.liqStr.ljust(n+9) + core2.liqStr)
    print()

def printDeltas(ccy,spotDict,spotDelta,futDelta):
  spot = spotDict[ccy]
  netDelta=spotDelta+futDelta
  nDigits=1 if ccy in ['BTC','ETH'] else None
  z=(ccy+' spot/fut/net delta: ').rjust(41)+(str(round(spotDelta,nDigits))+'/'+str(round(futDelta,nDigits))+'/'+str(round(netDelta,nDigits))).ljust(27) + \
    '($' + str(round(spotDelta * spot/1000)) + 'K/$' + str(round(futDelta * spot/1000)) + 'K/$' + str(round(netDelta * spot/1000)) + 'K)'
  print(termcolor.colored(z,'red'))

def printEURDeltas(krCores, spotDict):
  spotDelta=0
  for krCore in krCores:
    spotDelta+=krCore.spots.loc['EUR','SpotDelta']
  if spotDelta == 0 and CR_EXT_DELTA_EUR == 0: return
  netDelta= spotDelta + CR_EXT_DELTA_EUR
  z='EUR ext/impl/net delta: '.rjust(41) + (str(round(CR_EXT_DELTA_EUR / 1000)) + 'K/' + str(round(spotDelta / 1000)) + 'K/' + str(round(netDelta / 1000)) + 'K').ljust(27) + \
    '($' + str(round(CR_EXT_DELTA_EUR * spotDict['EUR'] / 1000)) + 'K/$' + str(round(spotDelta * spotDict['EUR'] / 1000)) + 'K/$' + str(round(netDelta * spotDict['EUR'] / 1000)) + 'K)'
  print(termcolor.colored(z,'red'))

def printUSDTDeltas(ftxCore,spotDict,usdtCoreList):
  realDelta_USD= ftxCore.wallet.loc['USDT','usdValue'] + CR_EXT_DELTA_USDT * spotDict['USDT']
  implDelta_USD=0
  for core in usdtCoreList:
    realDelta_USD+=core.nav
    implDelta_USD-=core.futures['FutDeltaUSD'].sum()
  netDelta_USD=realDelta_USD+implDelta_USD
  realDelta=realDelta_USD/spotDict['USDT']
  implDelta=implDelta_USD/spotDict['USDT']
  netDelta=realDelta+implDelta
  z1=str(round(realDelta/1000))+'K/'+str(round(implDelta/1000))+'K/'+str(round(netDelta/1000))+'K'
  z2='($'+str(round(realDelta_USD/1000))+'K/$'+str(round(implDelta_USD/1000))+'K/$'+ str(round(netDelta_USD/1000))+'K)'
  print(termcolor.colored('USDT real/impl/net delta: '.rjust(41)+z1.ljust(27)+z2, 'red'))

####################################################################################################

#########
# Classes
#########
class core:
  def __init__(self, exch, spotDict, n=None):
    self.exch = exch
    self.name = exch.upper()
    self.spotDict = spotDict
    if n is not None:
      self.n = n
      self.name += str(n)
    #####
    self.validCcys = []
    for ccy in INT_CCY_DICT.keys():
      if exch in INT_CCY_DICT[ccy]['exch']:
        self.validCcys.append(ccy)
    #####
    ccyList = list(INT_CCY_DICT.keys())
    if exch=='kr': ccyList.append('EUR')
    zeroes = [0] * len(ccyList)
    self.spots = pd.DataFrame({'Ccy': ccyList, 'SpotDelta': zeroes, 'SpotDeltaUSD':zeroes}).set_index('Ccy')
    self.futures = pd.DataFrame({'Ccy':ccyList, 'FutDelta': zeroes, 'FutDeltaUSD':zeroes}).set_index('Ccy')
    self.oneDayIncome = 0
    self.nav = 0
    self.fundingStrDict=dict()

  def run(self):
    if self.exch=='dummy': return
    if self.exch=='ftx':
      self.ftxInit()
    elif self.exch=='bb':
      self.bbInit()
    elif self.exch=='bbt':
      self.bbtInit()
    elif self.exch=='bn':
      self.bnInit()
    elif self.exch=='bnt':
      self.bntInit()
    elif self.exch=='db':
      self.dbInit()
    elif self.exch=='kf':
      self.kfInit()
    elif self.exch=='kr':
      self.krInit()

  def calcSpotDeltaUSD(self):
    for ccy in self.validCcys:
      self.spots.loc[ccy,'SpotDeltaUSD']=self.spots.loc[ccy,'SpotDelta']*self.spotDict[ccy]

  def calcFuturesDeltaUSD(self):
    for ccy in self.validCcys:
      self.futures.loc[ccy, 'FutDeltaUSD'] = self.futures.loc[ccy, 'FutDelta'] * self.spotDict[ccy]
    self.futNotional = self.futures['FutDeltaUSD'].abs().sum()

  def makeIncomesStr(self):
    z1 = '$' + str(round(self.oneDayIncome)) + ' (' + str(round(self.oneDayAnnRet * 100)) + '% p.a.)'
    if self.exch == 'db':
      self.incomesStr = termcolor.colored('DB 24h funding income: '.rjust(41) + z1, 'blue')
    else:
      zPrev  = '4h' if self.exch == 'kf' else 'prev'
      z2 = '$' + str(round(self.prevIncome)) + ' (' + str(round(self.prevAnnRet * 100)) + '% p.a.)'
      self.incomesStr = termcolor.colored((self.exch.upper() + ' 24h/'+zPrev+' funding income: ').rjust(41) + z1 + ' / ' + z2, 'blue')

  def makeFundingStr(self,ccy, oneDayFunding, prevFunding, estFunding, estFunding2=None):
    prefix = self.exch.upper() + ' ' + ccy + ' 24h/'
    if self.exch=='db':
      prefix+='8h'
    else:
      prefix+='prev'
    prefix+='/est'
    if self.exch in ['bb','bbt','kf']:
      prefix += '1/est2'
    prefix += ' funding rate:'
    #####
    body = str(round(oneDayFunding * 100)) + '%/'
    body += str(round(prevFunding * 100)) + '%/'
    body += str(round(estFunding * 100)) + '%'
    if self.exch in ['bb','bbt','kf']:
      body += '/' + str(round(estFunding2 * 100)) + '%'
    body += ' p.a.'
    #####
    spotDeltaUSD=self.spots.loc[ccy,'SpotDeltaUSD']
    futDeltaUSD=self.futures.loc[ccy, 'FutDeltaUSD']
    netDeltaUSD=spotDeltaUSD+futDeltaUSD
    if self.exch in ['bbt','bnt']:
      suffix = '(fut delta: $' + str(round(futDeltaUSD / 1000)) + 'K)'
    else:
      suffix = '(spot/fut/net delta: $' + str(round(spotDeltaUSD/1000)) + 'K/$' + str(round(futDeltaUSD/1000)) + 'K/$' + str(round(netDeltaUSD/1000))+'K)'
    self.fundingStrDict[ccy] = prefix.rjust(40) + ' ' + body.ljust(27) + suffix

  def makeLiqStr(self):
    if self.exch in ['ftx','bbt','bnt']:
      z = 'never' if (self.liq <= 0 or self.liq > 10) else str(round(self.liq * 100)) + '% (of spot)'
      zRet=termcolor.colored((self.exch.upper()+' liquidation (parallel shock): ').rjust(41) + z, 'red')
      if self.exch=='ftx':
        z = str(round(self.mf * 100, 1)) + '% (vs. ' + str(round(self.mmReq * 100, 1)) + '% limit) / $' + str(round(self.freeCollateral))
        zRet+='\n'+termcolor.colored('FTX margin fraction/free collateral: '.rjust(41) + z, 'red')
    else:
      zList=[]
      for ccy in self.validCcys:
        zList.append('never' if (self.liqDict[ccy] <= 0 or self.liqDict[ccy] >= 10) else str(round(self.liqDict[ccy] * 100)) + '%')
      zRet = termcolor.colored((self.exch.upper() + ' liquidation ('+'/'.join(self.validCcys)+'): ').rjust(41) + '/'.join(zList) + ' (of spot)', 'red')
    self.liqStr = zRet

  def printAll(self):
    if self.exch=='dummy': return
    print(self.incomesStr)
    for ccy in self.validCcys:
      print(self.fundingStrDict[ccy])
    print(self.liqStr)
    print()

  #####
  # FTX
  #####
  def ftxInit(self):
    def cleanBorrows(ccy, df):
      dummy = pd.DataFrame([[0, 0, 0, 0, 0, 0]], columns=['time', 'coin', 'size', 'rate', 'cost', 'proceeds'])
      if len(df) == 0:
        return dummy
      df2 = df.copy()
      df2 = df2[df2['coin'] == ccy]
      if len(df2) == 0:
        return dummy
      df2 = df2.set_index('time').sort_index()
      return df2
    ######
    def getBorrowsLoans(ccy):
      start_time = getYest()
      borrows = cleanBorrows(ccy, pd.DataFrame(self.api.private_get_spot_margin_borrow_history({'limit': 1000, 'start_time': start_time})['result']))
      loans = cleanBorrows(ccy, pd.DataFrame(self.api.private_get_spot_margin_lending_history({'limit': 1000, 'start_time': start_time})['result']))
      cl.dfSetFloat(borrows, 'cost')
      cl.dfSetFloat(loans, 'proceeds')
      prevBorrow = borrows.iloc[-1]['cost'] if borrows.index[-1] == self.payments.index[-1] else 0
      prevLoan = loans.iloc[-1]['proceeds'] if loans.index[-1] == self.payments.index[-1] else 0
      prevFlows = (prevLoan - prevBorrow) * self.spotDict[ccy]
      absBalance = abs(self.wallet.loc[ccy, 'total'])
      prevFlowsAnnRet = prevFlows * 24 * 365 / absBalance
      oneDayFlows = (loans['proceeds'].sum() - borrows['cost'].sum()) * self.spotDict[ccy]
      oneDayFlowsAnnRet = oneDayFlows * 365 / absBalance
      d=dict()
      d['prevFlows']=prevFlows
      d['prevFlowsAnnRet']=prevFlowsAnnRet
      d['oneDayFlows']=oneDayFlows
      d['oneDayFlowsAnnRet']=oneDayFlowsAnnRet
      return d
    ######
    self.api = cl.ftxCCXTInit()
    self.wallet = cl.ftxGetWallet(ftx)
    for ccy in self.validCcys:
      self.spots.loc[ccy,'SpotDelta'] = self.wallet.loc[ccy,'total']
    self.calcSpotDeltaUSD()
    ######
    info = self.api.private_get_account()['result']
    futs = pd.DataFrame(info['positions']).set_index('future')
    cl.dfSetFloat(futs, 'size')
    for ccy in self.validCcys:
      ccy2=ccy+'-PERP'
      mult = -1 if futs.loc[ccy2, 'side']=='sell' else 1
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'size']*mult
    self.calcFuturesDeltaUSD()
    ######
    pmts = pd.DataFrame(self.api.private_get_funding_payments({'limit': 1000, 'start_time': getYest()})['result'])
    pmts = pmts.set_index('future', drop=False).loc[[z+'-PERP' for z in self.validCcys]].set_index('time')
    cl.dfSetFloat(pmts, ['payment', 'rate'])
    pmts = pmts.sort_index()
    self.payments = pmts
    #####
    self.oneDayIncome = -pmts['payment'].sum()
    self.prevIncome = -pmts.loc[pmts.index[-1]]['payment'].sum()
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 24 * 365 / self.futNotional
    #####
    self.oneDayFlows=0
    self.flowsDict=dict()
    for ccy in CR_FTX_FLOWS_CCYS:
      d=getBorrowsLoans(ccy)
      self.flowsDict[ccy]=d
      self.oneDayFlows+=d['oneDayFlows']
    #####
    self.nav = self.wallet['usdValue'].sum()
    self.mf = float(info['marginFraction'])
    self.mmReq = float(info['maintenanceMarginRequirement'])
    totalPositionNotional = self.nav / self.mf
    cushion = (self.mf - self.mmReq) * totalPositionNotional
    totalDelta = self.wallet.loc[self.validCcys, 'usdValue'].sum() + self.futures['FutDeltaUSD'].sum()
    self.liq = 1 - cushion / totalDelta
    self.freeCollateral = float(info['freeCollateral'])
    #####
    for ccy in self.validCcys:
      df = pmts.loc[pmts['future'] == ccy + '-PERP', 'rate']
      oneDayFunding = df.mean() * 24 * 365
      prevFunding = df[df.index[-1]].mean() * 24 * 365
      estFunding = cl.ftxGetEstFunding(self.api, ccy)
      self.makeFundingStr(ccy,oneDayFunding,prevFunding,estFunding)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  def ftxPrintFlowsSummary(self,ccy):
    d = self.flowsDict[ccy]
    z1 = '$' + str(round(d['oneDayFlows'])) + ' (' + str(round(d['oneDayFlowsAnnRet'] * 100)) + '% p.a.)'
    z2 = '$' + str(round(d['prevFlows'])) + ' (' + str(round(d['prevFlowsAnnRet'] * 100)) + '% p.a.)'
    print(termcolor.colored(('FTX 24h/prev '+ccy+' flows: ').rjust(41) + z1 + ' / ' + z2, 'blue'))
  
  def ftxPrintBorrowLending(self, ccy, nav):
    estBorrow = cl.ftxGetEstBorrow(self.api,ccy)
    estLending = cl.ftxGetEstLending(self.api,ccy)
    n = self.wallet.loc[ccy, 'usdValue']
    suffix = '($' + str(round(n/1000))+'K) '
    suffix += '(' + str(round(n/nav*100))+'%)'
    print(('FTX '+ccy+' est borrow/lending rate: ').rjust(41) + (str(round(estBorrow * 100)) + '%/' + str(round(estLending * 100))+ '% p.a. '+suffix).ljust(27))
  
  def ftxPrintCoinLending(self, ccy):
    estLending = float(pd.DataFrame(self.api.private_get_spot_margin_lending_rates()['result']).set_index('coin').loc[ccy, 'estimate']) * 24 * 365
    coinBalance = self.wallet.loc[ccy, 'usdValue']
    print(('FTX '+ccy+' est lending rate: ').rjust(41) + str(round(estLending * 100)) + '% p.a. ($' + str(round(coinBalance/1000)) + 'K)')

  ####
  # BB
  ####
  def bbInit(self):
    def getPayments(ccy):
      n = 0
      df = pd.DataFrame()
      while True:
        n += 1
        tl = self.api.v2_private_get_execution_list({'symbol': ccy + 'USD', 'start_time': getYest() * 1000, 'limit': 1000, 'page': n})['result']['trade_list']
        if tl is None:
          break
        else:
          df = df.append(pd.DataFrame(tl))
      return df.set_index('symbol', drop=False)
    #####
    self.api = cl.bbCCXTInit()
    self.wallet=pd.DataFrame(self.api.v2_private_get_wallet_balance()['result']).transpose()
    cl.dfSetFloat(self.wallet,'equity')
    for ccy in self.validCcys:
      self.spots.loc[ccy,'SpotDelta']=self.wallet.loc[ccy,'equity']
    self.calcSpotDeltaUSD()
    #####
    self.liqDict=dict()
    futs = self.api.v2_private_get_position_list()['result']
    futs = pd.DataFrame([pos['data'] for pos in futs]).set_index('symbol')
    cl.dfSetFloat(futs, ['size','liq_price','position_value','unrealised_pnl'])
    for ccy in self.validCcys:
      ccy2=ccy+'USD'
      mult = -1 if futs.loc[ccy2,'side']=='Sell' else 1
      self.futures.loc[ccy, 'FutDelta'] = futs.loc[ccy2, 'size'] * mult / self.spotDict[ccy]
      self.liqDict[ccy] = futs.loc[ccy2,'liq_price'] / cl.bbGetMid(self.api,ccy)
    self.calcFuturesDeltaUSD()
    #####
    pmts = pd.DataFrame()
    for ccy in self.validCcys:
      pmts = pmts.append(getPayments(ccy))
    pmts = pmts[pmts['exec_type'] == 'Funding'].copy()
    cl.dfSetFloat(pmts, ['fee_rate', 'exec_fee'])
    pmts.loc[['Sell' in z for z in pmts['order_id']],'fee_rate']*=-1 # Correction for fee_rate signs
    for ccy in self.validCcys:
      ccy2=ccy+'USD'
      pmts.loc[ccy2, 'incomeUSD'] = -pmts.loc[ccy2, 'exec_fee'] * self.spotDict[ccy]
    pmts['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in pmts['trade_time_ms']]
    pmts = pmts.set_index('date')
    #####
    self.oneDayIncome = pmts['incomeUSD'].sum()
    self.prevIncome = pmts.loc[pmts.index[-1]]['incomeUSD'].sum()
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 3 * 365 / self.futNotional
    #####
    self.nav=self.spots['SpotDeltaUSD'].sum()
    #####
    for ccy in self.validCcys:
      df = pmts.loc[pmts['symbol'] == ccy + 'USD', 'fee_rate']
      oneDayFunding = df.mean() * 3 * 365
      prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.bbGetEstFunding1(self.api, ccy)
      estFunding2 = cl.bbGetEstFunding2(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding, estFunding2)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  #####
  # BBT
  #####
  def bbtInit(self):
    self.api = cl.bbCCXTInit()
    for ccy in self.validCcys:
      self.futures.loc[ccy, 'FutDelta']=cl.bbtGetFutPos(self.api,ccy)
    self.calcFuturesDeltaUSD()
    #####
    pmts=pd.DataFrame()
    for ccy in self.validCcys:
      pmts=pmts.append(pd.DataFrame(self.api.private_linear_get_trade_execution_list({'symbol': ccy + 'USDT', 'start_time': getYest() * 1000, 'exec_type':'Funding', 'limit': 1000})['result']['data']).set_index('symbol',drop=False))
    cl.dfSetFloat(pmts, ['fee_rate', 'exec_fee'])
    pmts.loc[['Sell' in z for z in pmts['order_id']],'fee_rate']*=-1 # Correction for fee_rate signs
    pmts['incomeUSD'] = -pmts['exec_fee'] * self.spotDict['USDT']
    pmts['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in pmts['trade_time_ms']]
    pmts = pmts.set_index('date').sort_index()
    #####
    self.oneDayIncome = pmts['incomeUSD'].sum()
    self.prevIncome = pmts.loc[pmts.index[-1]]['incomeUSD'].sum()
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 3 * 365 / self.futNotional
    #####
    walletUSDT = self.api.v2_private_get_wallet_balance({'coin': 'USDT'})['result']['USDT']
    self.nav=float(walletUSDT['equity'])*self.spotDict['USDT']
    cushion=float(walletUSDT['available_balance'])*self.spotDict['USDT']
    totalDelta = self.futures['FutDeltaUSD'].sum()
    self.liq = 1 - cushion / totalDelta
    #####
    for ccy in self.validCcys:
      df=pmts.loc[pmts['symbol']==ccy+'USDT','fee_rate']
      oneDayFunding = df.mean() * 3 * 365
      prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.bbtGetEstFunding1(self.api, ccy)
      estFunding2 = cl.bbtGetEstFunding2(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding, estFunding2)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  ####
  # BN
  ####
  def bnInit(self):
    self.api = cl.bnCCXTInit()
    bal = pd.DataFrame(self.api.dapiPrivate_get_balance())
    cl.dfSetFloat(bal, ['balance', 'crossUnPnl'])
    bal = bal.set_index('asset').loc[self.validCcys]
    for ccy in self.validCcys:
      self.spots.loc[ccy,'SpotDelta']=bal.loc[ccy,'balance']+bal.loc[ccy,'crossUnPnl']
    self.calcSpotDeltaUSD()
    #####
    self.liqDict = dict()
    futs = pd.DataFrame(self.api.dapiPrivate_get_positionrisk()).set_index('symbol')
    cl.dfSetFloat(futs, ['positionAmt','liquidationPrice','markPrice'])
    for ccy in self.validCcys:
      ccy2=ccy+'USD_PERP'
      mult=100 if ccy=='BTC' else 10 # ETH and XRP are 10 multipliers
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'positionAmt']*mult/self.spotDict[ccy]
      self.liqDict[ccy] = futs.loc[ccy2,'liquidationPrice'] / futs.loc[ccy2,'markPrice']
    self.calcFuturesDeltaUSD()
    #####
    pmts = pd.DataFrame()
    for ccy in self.validCcys:
      pmts = pmts.append(bnGetPayments(self.api,ccy))
    #####
    self.oneDayIncome,self.prevIncome=bnGetIncomes(self.api,self.validCcys,self.spotDict)
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 3 * 365 / self.futNotional
    #####
    self.nav = self.spots['SpotDeltaUSD'].sum()
    #####
    self.oneDayFundingDict = dict()
    self.prevFundingDict = dict()
    self.estFundingDict=dict()
    for ccy in self.validCcys:
      df = pmts.loc[pmts['symbol'] == ccy + 'USD_PERP', 'fundingRate']
      oneDayFunding = df.mean() * 3 * 365
      prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.bnGetEstFunding(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  #####
  # BNT
  #####
  def bntInit(self):
    self.api = cl.bnCCXTInit()
    futs = pd.DataFrame(self.api.fapiPrivate_get_positionrisk()).set_index('symbol')
    cl.dfSetFloat(futs, ['positionAmt'])
    for ccy in self.validCcys:
      ccy2=ccy+'USDT'
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'positionAmt']
    self.calcFuturesDeltaUSD()
    #####
    pmts=pd.DataFrame()
    for ccy in self.validCcys:
      pmts=pmts.append(bnGetPayments(self.api,ccy,isBNT=True))
    self.oneDayIncome,self.prevIncome=bnGetIncomes(self.api,self.validCcys,self.spotDict,isBNT=True)
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 3 * 365 / self.futNotional
    #####
    walletUSDT = pd.DataFrame(self.api.fapiPrivate_get_account()['assets']).set_index('asset').loc['USDT']
    self.nav = float(walletUSDT['marginBalance'])*self.spotDict['USDT']
    cushion = float(walletUSDT['availableBalance'])*self.spotDict['USDT']
    totalDelta = self.futures['FutDeltaUSD'].sum()
    self.liq = 1 - cushion / totalDelta
    #####
    for ccy in self.validCcys:
      df = pmts.loc[pmts['symbol'] == ccy + 'USDT', 'fundingRate']
      oneDayFunding = df.mean() * 3 * 365
      prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.bntGetEstFunding(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  ####
  # DB
  ####
  def dbInit(self):
    def getOneDayIncome(ccy, spot):
      df = pd.DataFrame(self.api.private_get_get_settlement_history_by_currency({'currency': ccy})['result']['settlements'])
      if len(df) == 0: return 0
      cl.dfSetFloat(df, 'funding')
      df['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in df['timestamp']]
      df = df.set_index('date').sort_index()
      if df.index[-1] >= (datetime.datetime.now() - pd.DateOffset(days=1)):
        return df['funding'].iloc[-1] * spot
      else:
        return 0
    #####
    self.api = cl.dbCCXTInit()
    self.liqDict = dict()
    for ccy in self.validCcys:
      acSum=self.api.private_get_get_account_summary({'currency': ccy})['result']
      self.spots.loc[ccy,'SpotDelta']=float(acSum['equity'])
      self.liqDict[ccy] = float(acSum['estimated_liquidation_ratio']) 
    self.calcSpotDeltaUSD()
    #####
    for ccy in self.validCcys:
      self.futures.loc[ccy, 'FutDelta']=cl.dbGetFutPos(self.api,ccy)/spotDict[ccy]
    self.calcFuturesDeltaUSD()
    #####
    self.oneDayIncome = getOneDayIncome('BTC', self.spotDict['BTC']) + getOneDayIncome('ETH', self.spotDict['ETH'])
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    #####
    self.nav = self.spots['SpotDeltaUSD'].sum()
    #####
    for ccy in self.validCcys:
      oneDayFunding = cl.dbGetEstFunding(self.api, ccy, mins=60 * 24)
      prevFunding = cl.dbGetEstFunding(self.api, ccy, mins=60 * 8)
      estFunding = cl.dbGetEstFunding(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  ####
  # KF
  ####
  def kfInit(self):
    def getPayments():
      if APOPHIS_IS_IP_WHITELIST:
        ffn = os.path.dirname(cl.__file__) + '\\data\kfLog.csv'
        self.api.get_account_log(ffn)
        df = pd.read_csv(ffn, index_col=0, parse_dates=True)
        df['date'] = [datetime.datetime.strptime(z, '%Y-%m-%d %H:%M:%S') for z in df['dateTime']]
        df['date'] += pd.DateOffset(hours=8)  # Convert from UTC to HK Time
        df = df[df['date'] >= datetime.datetime.now() - pd.DateOffset(days=1)]
        df['Ccy']=df['collateral']
        df.loc[df['Ccy']=='XBT','Ccy']='BTC'
        df=df.set_index('Ccy',drop=False)
        for ccy in self.validCcys:
          df.loc[ccy, 'Spot'] = self.spotDict[ccy]
        df['incomeUSD'] = df['realized funding'] * df['Spot']
        oneDayIncome = df['incomeUSD'].sum()
        prevIncome = df[df['date'] >= datetime.datetime.now() - pd.DateOffset(hours=4)]['incomeUSD'].sum()
        df=df[df['type']=='funding rate change'].set_index('date').sort_index()
        df['rate'] = df['funding rate'] * df['Spot'] * 8
        return df,oneDayIncome,prevIncome
      else:
        return None,0,0
    #####
    self.api = cl.kfApophisInit()
    accounts = self.api.query('accounts')['accounts']
    self.liqDict = dict()
    for ccy in self.validCcys:
      ccy2 = 'xbt' if ccy=='BTC' else ccy.lower()
      self.spots.loc[ccy,'SpotDelta'] = accounts['fi_'+ccy2+'usd']['auxiliary']['pv'] + accounts['cash']['balances'][ccy2]
      self.liqDict[ccy] = accounts['fi_' + ccy2 + 'usd']['triggerEstimates']['im'] / self.spotDict[ccy]
    self.calcSpotDeltaUSD()
    #####
    for ccy in self.validCcys:
      ccy2 = 'xbt' if ccy == 'BTC' else ccy.lower()
      self.futures.loc[ccy,'FutDelta']=accounts['fi_'+ccy2+'usd']['balances']['pi_'+ccy2+'usd']/spotDict[ccy]
    self.calcFuturesDeltaUSD()
    #####
    pmts,self.oneDayIncome,self.prevIncome=getPayments()
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 6 * 365 / self.futNotional
    #####
    self.nav = self.spots['SpotDeltaUSD'].sum()
    #####
    for ccy in self.validCcys:
      if pmts is None:
        oneDayFunding = 0
        prevFunding = 0
      else:
        df = pmts.loc[pmts['Ccy'] == ccy, 'rate']
        oneDayFunding = df.mean() * 3 * 365
        prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.kfGetEstFunding1(self.api, ccy)
      estFunding2 = cl.kfGetEstFunding2(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding, estFunding2)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()

  ####
  # KR
  ####
  def krInit(self):
    def getBal(bal, ccy):
      try:
        return float(bal[CR_KR_CCY_DICT[ccy]])
      except:
        return 0
    #####
    self.api = cl.krCCXTInit(self.n)
    bal = self.api.private_post_balance()['result']
    for ccy in CR_KR_CCY_DICT.keys():
      self.spots.loc[ccy,'SpotDelta']=getBal(bal,ccy)
    #####
    positions = pd.DataFrame(self.api.private_post_openpositions()['result']).transpose().set_index('pair')
    if not all([z in ['XXBTZUSD', 'XXBTZEUR'] for z in positions.index]):
      print('Invalid Kraken pair detected!')
      sys.exit(1)
    cl.dfSetFloat(positions, ['vol', 'vol_closed', 'time'])
    positions['date'] = [datetime.datetime.fromtimestamp(int(ts)) for ts in positions['time']]
    positions['volNetBTC'] = positions['vol'] - positions['vol_closed']
    positions['volNetUSD'] = positions['volNetBTC'] * self.spotDict['BTC']
    self.spots.loc['BTC','SpotDelta'] += positions['volNetBTC'].sum()
    if 'XXBTZEUR' in positions.index:
      self.spots.loc['EUR','SpotDelta'] -= positions.loc['XXBTZEUR', 'volNetBTC'].sum() * float(self.api.public_get_ticker({'pair': 'XXBTZEUR'})['result']['XXBTZEUR']['c'][0])
    for ccy in CR_KR_CCY_DICT.keys():
      self.spots.loc[ccy,'SpotDeltaUSD']=self.spots.loc[ccy,'SpotDelta']*self.spotDict[ccy]
    notional = positions['volNetUSD'].abs().sum()
    #####
    # mdbUSD=Margin Delta BTC in USD
    xxbtzeur_volNetUSD_sum = positions.loc['XXBTZEUR', 'volNetUSD'].sum() if 'XXBTZEUR' in positions.index else 0
    self.mdbUSDDf = pd.DataFrame([['USD', positions.loc['XXBTZUSD', 'volNetUSD'].sum()], ['EUR', xxbtzeur_volNetUSD_sum]], columns=['Ccy', 'MDBU']).set_index('Ccy')
    #####
    self.oneDayIncome = -self.mdbUSDDf['MDBU'].sum() * 0.0006
    self.oneDayAnnRet = self.oneDayIncome * 365 / notional
    #####
    tradeBal = self.api.private_post_tradebalance()['result']
    self.nav = float(tradeBal['eb'])+float(tradeBal['n'])
    #####
    freeMargin = float(tradeBal['mf'])
    self.liqBTC = 1 - freeMargin / self.spots.loc['BTC','SpotDeltaUSD']

  def krPrintBorrow(self, nav):
    d=CR_KR_CCY_DICT.copy()
    del d['EUR']
    zList=[]
    for ccy in d.keys():
      zList.append('$'+str(round(self.spots.loc[ccy,'SpotDeltaUSD']/1000))+'K')
    zPctNAV = '('+str(round(-self.mdbUSDDf['MDBU'].sum() / nav*100))+'%)'
    suffix='(spot '+'/'.join(d.keys())+': '
    suffix+='/'.join(zList)
    suffix+='; XXBTZUSD/XXBTZEUR: $'
    suffix += str(round(self.mdbUSDDf.loc['USD', 'MDBU'] / 1000)) + 'K/$'
    suffix += str(round(self.mdbUSDDf.loc['EUR', 'MDBU'] / 1000)) + 'K)'
    print(('KR' + str(self.n) + ' USD/EUR est borrow rate: ').rjust(41) + ('22% p.a. ($' + str(round(-self.mdbUSDDf['MDBU'].sum()/1000)) + 'K) '+zPctNAV).ljust(27)+suffix)

####################################################################################################

######
# Init
######
cl.printHeader('CryptoReporter')
if CRYPTO_MODE>0 and not APOPHIS_IS_IP_WHITELIST:
  print('[ERROR: IP is not whitelisted for Apophis, therefore KF incomes are not shown]')
  print()
ftx=cl.ftxCCXTInit()
spotDict=dict()
spotDict['USD']=1
for ccy in CR_QUOTE_CCY_DICT.keys():
  spotDict[ccy]=cl.ftxGetMid(ftx,ccy+'/USD')
#####
ftxCore = core('ftx',spotDict)
bbCore = core('bb',spotDict)
objs=[ftxCore,bbCore]
krCores=[]
if CRYPTO_MODE>0:
  bbtCore = core('bbt', spotDict)
  bnCore = core('bn', spotDict)
  bntCore = core('bnt', spotDict)
  dbCore = core('db', spotDict)
  kfCore = core('kf', spotDict)
  for i in range(CR_N_KR_ACCOUNTS):
    krCores.append(core('kr',spotDict,n=i+1))
  objs.extend([bbtCore, bnCore, bntCore, dbCore, kfCore] + krCores)
Parallel(n_jobs=len(objs), backend='threading')(delayed(obj.run)() for obj in objs)

#############
# Aggregation
#############
agDf = pd.DataFrame({'Ccy': CR_AG_CCY_DICT.keys(), 'SpotDelta': CR_AG_CCY_DICT.values(), 'FutDelta': [0] * len(CR_AG_CCY_DICT.keys())}).set_index('Ccy')
nav=0
oneDayIncome=0
for obj in objs:
  nav+=obj.nav
  oneDayIncome += obj.oneDayIncome
  for ccy in CR_AG_CCY_DICT.keys():
    agDf.loc[ccy,'SpotDelta']+=obj.spots.loc[ccy,'SpotDelta']
    agDf.loc[ccy,'FutDelta']+=obj.futures.loc[ccy,'FutDelta']
extCoinsNAV=0
for ccy in CR_AG_CCY_DICT.keys():
  extCoinsNAV += CR_AG_CCY_DICT[ccy] * spotDict[ccy]
extUSDTNAV = CR_EXT_DELTA_USDT * spotDict['USDT']
extEURNAV = CR_EXT_DELTA_EUR * (spotDict['EUR'] - CR_EXT_DELTA_EUR_REF)
nav+= extCoinsNAV + extUSDTNAV + extEURNAV
oneDayIncome+=ftxCore.oneDayFlows

########
# Output
########
navStrList=[]
for obj in objs:
  navStrList.append(getNAVStr(obj.name,obj.nav))
if extCoinsNAV!=0: navStrList.append(getNAVStr('Coins ext', extCoinsNAV))
if extEURNAV!=0: navStrList.append(getNAVStr('EUR ext', extEURNAV))
print(termcolor.colored(('NAV as of '+cl.getCurrentTime()+': $').rjust(42)+str(round(nav))+' ('+' / '.join(navStrList)+')','blue'))
#####
zList=[]
for ccy in CR_QUOTE_CCY_DICT.keys():
  zList.append(ccy + '=' + str(round(spotDict[ccy], CR_QUOTE_CCY_DICT[ccy])))
print(termcolor.colored('24h income: $'.rjust(42)+(str(round(oneDayIncome))+' ('+str(round(oneDayIncome*365/nav*100))+'% p.a.)').ljust(26),'blue')+' / '.join(zList))
print()
#####
for ccy in CR_AG_CCY_DICT.keys():
  printDeltas(ccy,spotDict,agDf.loc[ccy,'SpotDelta'],agDf.loc[ccy,'FutDelta'])
if CRYPTO_MODE>0:
  printUSDTDeltas(ftxCore, spotDict, [bbtCore, bntCore])
  printEURDeltas(krCores, spotDict)
print()
#####
ftxCore.ftxPrintFlowsSummary('USD')
ftxCore.ftxPrintFlowsSummary('USDT')
ftxCore.ftxPrintBorrowLending('USD',nav)
ftxCore.ftxPrintBorrowLending('USDT',nav)
print()
#####
if CR_IS_SHOW_COIN_LENDING:
  for ccy in CR_FTX_FLOWS_CCYS:
    if not ccy in ['USD','USDT']:
      ftxCore.ftxPrintFlowsSummary(ccy)
  print()
#####
ftxCore.printAll()
if CRYPTO_MODE>0:
  printAllDual(bbCore, bbtCore)
  printAllDual(bnCore, bntCore)
  dbCore.printAll()
  kfCore.printAll()
  krPrintAll(krCores, nav)
else:
  bbCore.printAll()
#####
if '-f' in sys.argv:
  while True:
    time.sleep(1)