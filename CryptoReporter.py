from CryptoParams import *
import CryptoLib as cl
from joblib import Parallel, delayed
import pandas as pd
import datetime
import time
import termcolor
import sys

###########
# Functions
###########
def bnGetPayments(bn, ccy, isBNT=False):
  if isBNT:
    df = pd.DataFrame(bn.fapiPublic_get_fundingrate({'symbol': ccy + 'USDT', 'startTime': cl.getYest() * 1000}))
  else:
    df = pd.DataFrame(bn.dapiPublic_get_fundingrate({'symbol': ccy + 'USD_PERP', 'startTime': cl.getYest() * 1000}))
  cl.dfSetFloat(df, 'fundingRate')
  df['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in df['fundingTime']]
  df = df.set_index('date').sort_index()
  return df

def bnGetIncomes(bn, validCcys, spotDict, isBNT=False):
  if isBNT:
    df = pd.DataFrame(bn.fapiPrivate_get_income({'incomeType': 'FUNDING_FEE', 'startTime': cl.getYest() * 1000})).set_index('symbol')
  else:
    df = pd.DataFrame(bn.dapiPrivate_get_income({'incomeType': 'FUNDING_FEE', 'startTime': cl.getYest() * 1000}))
    if len(df) == 0: return 0, 0
    df = df.set_index('symbol')
  cl.dfSetFloat(df, 'income')
  suffix = 'USDT' if isBNT else 'USD_PERP'
  validCcys=list(set(z.replace(suffix,'') for z in df.index).intersection(validCcys)) # Remove currencies without cashflows
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

def colored(text, color):
  if '--nocolor' in sys.argv:
    return text
  else:
    return termcolor.colored(text,color)

def fmtLiq(liq):
  return 'never' if (liq <= 0 or liq >= 10) else str(round(liq * 100)) + '%'

def getCores():
  def processCore(exch,spotDict,objs):
    if SHARED_EXCH_DICT[exch]==1:
      myCore=core(exch,spotDict)
    else:
      myCore=core('dummy',spotDict)
    objs.append(myCore)
    return myCore
  #####
  isOk=True
  ftx=cl.ftxCCXTInit()
  spotDict=dict()
  ccyList = list(CR_QUOTE_CCY_DICT.keys())
  if not 'BNB' in ccyList: ccyList.append('BNB')
  for ccy in ccyList:
    spotDict[ccy]=cl.ftxGetMid(ftx,ccy+'/USD')
  spotDict['USD']=1
  #####
  objs = []
  ftxCore=processCore('ftx',spotDict,objs)
  bbCore=processCore('bb',spotDict,objs)
  bbtCore=processCore('bbt',spotDict,objs)
  bnCore=processCore('bn',spotDict,objs)
  bntCore=processCore('bnt',spotDict,objs)
  kfCore=processCore('kf',spotDict,objs)
  krCores = []
  if SHARED_EXCH_DICT['kr'] >= 1:
    for i in range(SHARED_EXCH_DICT['kr']):
      krCores.append(core('kr',spotDict,n=i+1))
    objs.extend(krCores)
  try:
    Parallel(n_jobs=len(objs), backend='threading')(delayed(obj.run)() for obj in objs)
  except:
    print('[WARNING: Parallel run failed!  Rerunning in serial ....]')
    isOk = False
    for obj in objs:
      try:
        obj.run()
      except:
        pass
      if not obj.isDone:
        print('[WARNING: Corrupted results for ' + obj.name + '!]')
    print()
  return isOk, ftxCore, bbCore, bbtCore, bnCore, bntCore, kfCore, krCores, spotDict, objs

def getNAVStr(name, nav):
  return name + ': $' + str(round(nav/1000)) + 'K'

def krPrintAll(krCores,nav):
  # Incomes
  zList = []
  prefixList = []
  for krCore in krCores:
    zList.append('$' + str(round(krCore.oneDayIncome)) + ' (' + str(round(krCore.oneDayAnnRet * 100)) + '% p.a.)')
    prefixList.append('KR' + str(krCore.n))
  print(colored(('/'.join(prefixList) + ' 24h rollover fees: ').rjust(37) + ' / '.join(zList), 'blue'))
  #####
  # Borrows
  for krCore in krCores:
    krCore.krPrintBorrow(nav)

def printAllDual(core1, core2):
  if core1.exch == 'dummy' and core2.exch == 'dummy': return
  if core1.exch == 'dummy':
    core2.printAll()
  elif core2.exch == 'dummy':
    core1.printAll()
  else:
    n=120
    print(core1.incomesStr.ljust(n) + core2.incomesStr)
    list1 = list(core1.fundingStrDict.values())
    list2 = list(core2.fundingStrDict.values())
    list1.append(core1.liqStr.ljust(n))
    list2.append(core2.liqStr)
    for i in range(min(len(list1),len(list2))):
      print(list1[i].ljust(n) + list2[i])
    if len(list1)>len(list2):
      for i in range(len(list2),len(list1)):
        print(list1[i].ljust(n))
    elif len(list2)>len(list1):
      for i in range(len(list1),len(list2)):
        print(''.ljust(n) + list2[i])
    print()

def printDeltas(ccy,spotDict,spotDelta,futDelta):
  spot = spotDict[ccy]
  netDelta=spotDelta+futDelta
  if ccy=='BTC':
    nDigits=2
  elif ccy=='XRP':
    nDigits=None
  else:
    nDigits=1
  z=(ccy+' spot/fut/net: ').rjust(37)+(str(round(spotDelta,nDigits))+'/'+str(round(futDelta,nDigits))+'/'+str(round(netDelta,nDigits))).ljust(27) + \
    '($' + str(round(spotDelta * spot/1000)) + 'K/$' + str(round(futDelta * spot/1000)) + 'K/$' + str(round(netDelta * spot/1000)) + 'K)'
  print(colored(z,'red'))

def printUSDTDeltas(ftxCore,bnCore,spotDict,usdtCoreList):
  spotDeltaUSD = ftxCore.spots.loc['USDT','SpotDeltaUSD'] + CR_EXT_DELTA_USDT * spotDict['USDT']
  futDeltaUSD = ftxCore.futures.loc['USDT','FutDeltaUSD']
  implDeltaUSD=0
  for core in usdtCoreList:
    spotDeltaUSD+=core.spots.loc['USDT','SpotDeltaUSD']
    implDeltaUSD-=core.futures['FutDeltaUSD'].sum()
  imDeltaUSD = bnCore.spots.loc['USDT', 'SpotDeltaUSD']
  netDeltaUSD=spotDeltaUSD+futDeltaUSD+imDeltaUSD+implDeltaUSD
  #####
  spotDelta=spotDeltaUSD/spotDict['USDT']
  futDelta=futDeltaUSD/spotDict['USDT']
  implDelta=implDeltaUSD/spotDict['USDT']
  imDelta=imDeltaUSD/spotDict['USDT']
  netDelta=netDeltaUSD/spotDict['USDT']
  #####
  zLabel = 'spot/fut/impl/'
  z1=str(round(spotDelta/1000))+'K/'+str(round(futDelta/1000))+'K/'+str(round(implDelta/1000))+'K/'
  z2='($'+str(round(spotDeltaUSD/1000))+'K/$'+str(round(futDeltaUSD/1000))+'K/$'+str(round(implDeltaUSD/1000))+'K/$'
  if imDelta!=0:
    zLabel += 'im/'
    z1+= str(round(imDelta / 1000)) + 'K/'
    z2+= str(round(imDeltaUSD / 1000)) + 'K/$'
  zLabel += 'net: '
  z1 += str(round(netDelta / 1000)) + 'K'
  z2 += str(round(netDeltaUSD/1000))+'K)'
  print(colored(('USDT '+zLabel).rjust(37)+z1.ljust(27)+z2, 'red'))

def printFlows(ftxCore,bnCore,nav):
  def getSuffix(ftxCore,ccy,nav):
    return '(' + str(round(ftxCore.wallet.loc[ccy, 'usdValue'] / nav * 100)) + '%)'
  #####
  try:
    print(ftxCore.flowsDict['USD'])
    print(ftxCore.flowsDict['USDT'])
    print(ftxCore.flowsDict['USD2']+getSuffix(ftxCore,'USD',nav))
    print(ftxCore.flowsDict['USDT2']+getSuffix(ftxCore,'USDT',nav))
    print()
    #####
    isPrinted=False
    for ccy in CR_FTX_FLOWS_CCYS:
      z = ftxCore.flowsDict[ccy]
      if not z is None:
        isPrinted=True
        print(z)
    #####
    if CR_IS_ENABLE_BN_ISOLATED_MARGIN:
      isPrinted=True
      for symbol in bnCore.imDf.index:
        z1 = '$' + str(round(bnCore.imDf.loc[symbol,'oneDayFlows'])) + ' (' + str(round(bnCore.imDf.loc[symbol,'oneDayFlowsAnnRet'] * 100)) + '% p.a.)'
        z2 = '$' + str(round(bnCore.imDf.loc[symbol,'prevFlows'])) + ' (' + str(round(bnCore.imDf.loc[symbol,'prevFlowsAnnRet'] * 100)) + '% p.a.)'
        z3 = ' ($' + str(round(bnCore.imDf.loc[symbol,'qty']*bnCore.spotDict[bnCore.imDf.loc[symbol,'symbolAsset']]/1000))+'K)'
        print(colored(fmtLiq(bnCore.imDf.loc[symbol,'liq']).rjust(5),'red'),end='')
        print(colored(('BN 24h/prev '+symbol+' flows: ').rjust(32) + z1 + ' / ' + z2, 'blue')+z3)
    #####
    if isPrinted: print()
  #####
  except:
    pass

####################################################################################################

#########
# Classes
#########
class core:
  def __init__(self, exch, spotDict, n=None):
    self.isDone = False
    self.exch = exch
    self.name = exch.upper()
    self.spotDict = spotDict
    if n is not None:
      self.n = n
      self.name += str(n)
    #####
    self.validCcys = cl.getValidCcys(exch)
    #####
    ccyList = list(SHARED_CCY_DICT.keys())
    cl.appendUnique(ccyList, 'USDT')
    zeroes = [0] * len(ccyList)
    self.spots = pd.DataFrame({'Ccy': ccyList, 'SpotDelta': zeroes, 'SpotDeltaUSD':zeroes}).set_index('Ccy')
    self.futures = pd.DataFrame({'Ccy':ccyList, 'FutDelta': zeroes, 'FutDeltaUSD':zeroes}).set_index('Ccy')
    self.oneDayFlows = 0
    self.flowsDict = dict()
    self.oneDayIncome = 0
    self.nav = 0
    self.incomesStr = ''
    self.fundingStrDict=dict()
    self.liqDict=dict()
    self.liqStr = ''

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
    elif self.exch=='kf':
      self.kfInit()
    elif self.exch=='kr':
      self.krInit()

  def calcSpotDeltaUSD(self):
    for ccy in self.spots.index:
      self.spots.loc[ccy,'SpotDeltaUSD']=self.spots.loc[ccy,'SpotDelta']*self.spotDict[ccy]

  def calcFuturesDeltaUSD(self):
    for ccy in self.spots.index:
      self.futures.loc[ccy, 'FutDeltaUSD'] = self.futures.loc[ccy, 'FutDelta'] * self.spotDict[ccy]
    self.futNotional = self.futures['FutDeltaUSD'].abs().sum()

  def makeIncomesStr(self):
    z1 = '$' + str(round(self.oneDayIncome)) + ' (' + str(round(self.oneDayAnnRet * 100)) + '% p.a.)'
    zPrev  = '4h' if self.exch == 'kf' else 'prev'
    z2 = '$' + str(round(self.prevIncome)) + ' (' + str(round(self.prevAnnRet * 100)) + '% p.a.)'
    self.incomesStr = colored((self.exch.upper() + ' 24h/'+zPrev+' funding income: ').rjust(37) + z1 + ' / ' + z2, 'blue')

  def makeFundingStr(self,ccy, oneDayFunding, prevFunding, estFunding, estFunding2=None):
    if self.exch in ['bb','bbt','bn','bnt','kf']:
      z = fmtLiq(self.liqDict[ccy])
    else:
      z = ''
    liqStr = colored(z.rjust(5),'red')
    prefix = self.exch.upper() + ' ' + ccy + ' 24h/'
    prefix+='prev'
    prefix+='/est'
    if self.exch in ['bb','bbt','kf']:
      prefix += '1/est2'
    prefix += ':'
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
    if CR_IS_ENABLE_BN_ISOLATED_MARGIN and self.exch == 'bn' and ccy == 'BTC':
      imUSD = self.imDf['collateralBTC'].sum() * self.spotDict['BTC']
      spotDeltaUSD -= imUSD
      suffix = '(spot/fut/im/net: $' + str(round(spotDeltaUSD / 1000)) + 'K/$' + str(round(futDeltaUSD / 1000)) + 'K/$' + str(round(imUSD / 1000)) + 'K/$' + str(round(netDeltaUSD / 1000)) + 'K)'
    elif self.exch == 'bbt' or (self.exch == 'bnt' and ccy != 'BNB'):
      suffix = '(fut: $' + str(round(futDeltaUSD / 1000)) + 'K)'
    else:
      suffix = '(spot/fut/net: $' + str(round(spotDeltaUSD/1000)) + 'K/$' + str(round(futDeltaUSD/1000)) + 'K/$' + str(round(netDeltaUSD/1000))+'K)'
    self.fundingStrDict[ccy] = liqStr.rjust(5) + prefix.rjust(31) + ' ' + body.ljust(27) + suffix

  def makeLiqStr(self):
    z = fmtLiq(self.liq)
    if self.exch=='ftx':
      z2 = (self.exch.upper() + ' liq/mf/fc: ').rjust(37) + z + '/'
      z2 += str(round(self.mf * 100, 1)) + '%(vs.' + str(round(self.mmReq * 100, 1)) + '%)/$' + str(round(self.freeCollateral))
      self.liqStr = colored(z2,'red')
    else:
      self.liqStr = colored((self.exch.upper() + ' liq: ').rjust(37) + z, 'red')

  def printAll(self):
    try:
      if self.exch=='dummy': return
      print(self.incomesStr)
      for ccy in self.validCcys:
        print(self.fundingStrDict[ccy])
      if self.liqStr!='': print(self.liqStr)
      print()
    except:
      pass

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
    def makeFlows(ccy):
      start_time = cl.getYest()
      borrows = cleanBorrows(ccy, pd.DataFrame(self.api.private_get_spot_margin_borrow_history({'limit': 1000, 'start_time': start_time})['result']))
      loans = cleanBorrows(ccy, pd.DataFrame(self.api.private_get_spot_margin_lending_history({'limit': 1000, 'start_time': start_time})['result']))
      cl.dfSetFloat(borrows, ['cost','rate'])
      cl.dfSetFloat(loans, 'proceeds')
      prevBorrow = borrows.iloc[-1]['cost'] if borrows.index[-1] == self.payments.index[-1] else 0
      prevLoan = loans.iloc[-1]['proceeds'] if loans.index[-1] == self.payments.index[-1] else 0
      absBalUSD = abs(self.wallet.loc[ccy, 'total']*self.spotDict[ccy])
      d=dict()
      d['oneDayFlows'] = (loans['proceeds'].sum() - borrows['cost'].sum()) * self.spotDict[ccy]
      d['oneDayFlowsAnnRet'] = d['oneDayFlows'] * 365 / absBalUSD
      d['oneDayBorrowRate'] = borrows['rate'].mean() * 24 * 365
      d['prevFlows']=(prevLoan - prevBorrow) * self.spotDict[ccy]
      d['prevFlowsAnnRet']=d['prevFlows'] * 24 * 365 / absBalUSD
      d['prevBorrowRate'] = borrows.iloc[-1]['rate'] * 24 * 365 if borrows.index[-1] == self.payments.index[-1] else 0
      return d
    ######
    self.api = cl.ftxCCXTInit()
    self.wallet = cl.ftxGetWallet(self.api)
    ccys=self.validCcys.copy()
    cl.appendUnique(ccys,'USDT')
    for ccy in ccys:
      self.spots.loc[ccy,'SpotDelta'] = self.wallet.loc[ccy,'total']
    self.calcSpotDeltaUSD()
    ######
    info = self.api.private_get_account()['result']
    futs = pd.DataFrame(info['positions']).set_index('future')
    cl.dfSetFloat(futs, 'size')
    ccys=self.validCcys.copy()
    if 'USDT-PERP' in futs.index: cl.appendUnique(ccys,'USDT')
    for ccy in ccys:
      ccy2=ccy+'-PERP'
      mult = -1 if futs.loc[ccy2, 'side']=='sell' else 1
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'size']*mult
    self.calcFuturesDeltaUSD()
    ######
    pmts = pd.DataFrame(self.api.private_get_funding_payments({'limit': 1000, 'start_time': cl.getYest()})['result'])
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
    flowsCcy=CR_FTX_FLOWS_CCYS.copy()
    cl.appendUnique(flowsCcy,'USD')
    cl.appendUnique(flowsCcy,'USDT')
    for ccy in flowsCcy:
      d=makeFlows(ccy)
      self.oneDayFlows += d['oneDayFlows']
      if d['oneDayFlows']==0 and d['prevFlows']==0 and not ccy in ['USD','USDT']:
        self.flowsDict[ccy]=None
      else:
        z1 = '$' + str(round(d['oneDayFlows'])) + ' (' + str(round(d['oneDayFlowsAnnRet'] * 100)) + '% p.a.)'
        z2 = '$' + str(round(d['prevFlows'])) + ' (' + str(round(d['prevFlowsAnnRet'] * 100)) + '% p.a.)'
        self.flowsDict[ccy]=colored(('FTX 24h/prev ' + ccy + ' flows: ').rjust(37) + z1 + ' / ' + z2, 'blue')
      if ccy in ['USD','USDT']: # Extra info for USD/USDT
        zList = []
        zList.append('na' if d['oneDayBorrowRate'] == 0 else str(round(d['oneDayBorrowRate'] * 100)) + '%')
        zList.append('na' if d['prevBorrowRate'] == 0 else str(round(d['prevBorrowRate'] * 100)) + '%')
        zList.append(str(round(cl.ftxGetEstBorrow(self.api, ccy) * 100)) + '%')
        self.flowsDict[ccy+'2'] = ('FTX ' + ccy + ' 24h/prev/est: ').rjust(37) + '/'.join(zList) + ' p.a. ($' + str(round(self.wallet.loc[ccy, 'usdValue'] / 1000)) + 'K) '
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
    self.isDone=True

  ####
  # BB
  ####
  def bbInit(self):
    def getPayments(ccy):
      n = 0
      df = pd.DataFrame()
      while True:
        n += 1
        tl = self.api.v2_private_get_execution_list({'symbol': ccy + 'USD', 'start_time': cl.getYest() * 1000, 'limit': 1000, 'page': n})['result']['trade_list']
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
    self.isDone = True

  #####
  # BBT
  #####
  def bbtInit(self):
    self.api = cl.bbCCXTInit()
    riskDf = cl.bbtGetRiskDf(self.api, self.validCcys, self.spotDict)
    for ccy in self.validCcys:
      self.futures.loc[ccy, 'FutDelta']=cl.bbtGetFutPos(self.api,ccy)
      self.liqDict[ccy] = riskDf.loc[ccy,'liq']
    self.calcFuturesDeltaUSD()
    #####
    pmts=pd.DataFrame()
    for ccy in self.validCcys:
      data = self.api.private_linear_get_trade_execution_list({'symbol': ccy + 'USDT', 'start_time': cl.getYest() * 1000, 'exec_type': 'Funding', 'limit': 1000})['result']['data']
      if not data is None:
        pmts = pmts.append(pd.DataFrame(data).set_index('symbol', drop=False))
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
    wb = self.api.v2_private_get_wallet_balance({'coin': 'USDT'})['result']['USDT']
    equity = float(wb['equity'])
    self.nav = equity * self.spotDict['USDT']
    self.spots.loc['USDT', 'SpotDelta'] = equity
    self.calcSpotDeltaUSD()
    #####
    # Liquidation (parallel) calc
    wallet_balance = float(wb['wallet_balance'])
    increment = -0.01 if riskDf['delta_value'].sum() >= 0 else 0.01
    for i in range(100):
      riskDf['unrealised_pnl_sim'] = riskDf['unrealised_pnl'] + riskDf['delta_value'] * (i+1) * increment
      ab = wallet_balance - riskDf['im_value'].sum() + riskDf['unrealised_pnl_sim'].clip(None, 0).sum()
      riskDf['cushion'] = ab + riskDf['im_value'] - riskDf['mm_value'] + riskDf['unrealised_pnl_sim'].clip(0, None)
      if riskDf['cushion'].min() < 0: break
    self.liq = 1 + i * increment
    #####
    for ccy in self.validCcys:
      df=pmts.loc[pmts['symbol']==ccy+'USDT','fee_rate']
      if len(df) == 0:
        oneDayFunding = 0
        prevFunding = 0
      else:
        oneDayFunding = df.mean() * 3 * 365
        prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.bbtGetEstFunding1(self.api, ccy)
      estFunding2 = cl.bbtGetEstFunding2(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding, estFunding2)
    #####
    self.makeIncomesStr()
    self.makeLiqStr()
    self.isDone = True

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
    #####
    if CR_IS_ENABLE_BN_ISOLATED_MARGIN:
      self.imDf = cl.bnGetIsolatedMarginDf(self.api,self.spotDict)
      df=self.imDf.set_index('symbolAsset',drop=False)
      for i in range(len(df)):
        self.spots.loc[df.iloc[i]['symbolAsset'], 'SpotDelta'] += df.iloc[i]['qty']
      self.spots.loc['USDT', 'SpotDelta'] += df['collateralUSDT'].sum()
      self.spots.loc['BTC', 'SpotDelta'] += df['collateralBTC'].sum()
      self.oneDayFlows += self.imDf['oneDayFlows'].sum()
    #####
    self.calcSpotDeltaUSD()
    #####
    futs = pd.DataFrame(self.api.dapiPrivate_get_positionrisk()).set_index('symbol')
    cl.dfSetFloat(futs, ['positionAmt','liquidationPrice','markPrice'])
    for ccy in self.validCcys:
      ccy2=ccy+'USD_PERP'
      mult=100 if ccy=='BTC' else 10 # Only BTC is 100 multiplier
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'positionAmt']*mult/self.spotDict[ccy]
      self.liqDict[ccy] = futs.loc[ccy2,'liquidationPrice'] / futs.loc[ccy2,'markPrice']
    self.calcFuturesDeltaUSD()
    #####
    pmts = pd.DataFrame()
    for ccy in self.validCcys:
      pmts = pmts.append(bnGetPayments(self.api,ccy))
    #####
    self.oneDayIncome,self.prevIncome=bnGetIncomes(self.api,self.validCcys,self.spotDict)
    if self.futNotional==0:
      self.oneDayAnnRet=0
      self.prevAnnRet=0
    else:
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
    #####
    self.isDone = True

  #####
  # BNT
  #####
  def bntInit(self):
    self.api = cl.bnCCXTInit()
    riskDf = cl.bntGetRiskDf(self.api, self.validCcys)
    futs = pd.DataFrame(self.api.fapiPrivate_get_positionrisk()).set_index('symbol')
    cl.dfSetFloat(futs, ['positionAmt'])
    for ccy in self.validCcys:
      ccy2=ccy+'USDT'
      self.futures.loc[ccy,'FutDelta']=futs.loc[ccy2,'positionAmt']
      self.liqDict[ccy] = riskDf.loc[ccy+'USDT', 'liq']
    self.calcFuturesDeltaUSD()
    #####
    pmts=pd.DataFrame()
    for ccy in self.validCcys:
      pmts=pmts.append(bnGetPayments(self.api,ccy,isBNT=True))
    self.oneDayIncome,self.prevIncome=bnGetIncomes(self.api,self.validCcys,self.spotDict,isBNT=True)
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 3 * 365 / self.futNotional
    #####
    d=self.api.fapiPrivate_get_account()
    mb = float(d['totalMarginBalance'])
    mm = float(d['totalMaintMargin'])
    self.spots.loc['USDT','SpotDelta'] = mb
    self.spots.loc['BNB','SpotDelta'] = float(pd.DataFrame(d['assets']).set_index('asset').loc['BNB', 'walletBalance'])
    self.calcSpotDeltaUSD()
    self.nav = self.spots.loc[['USDT','BNB'],'SpotDeltaUSD'].sum()
    cushion = (mb-mm) * self.spotDict['USDT']
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
    self.isDone = True

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
          if ccy in df.index: df.loc[ccy, 'Spot'] = self.spotDict[ccy]
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
    for ccy in self.validCcys:
      ccy2 = 'xbt' if ccy=='BTC' else ccy.lower()
      self.spots.loc[ccy,'SpotDelta'] = accounts['fi_'+ccy2+'usd']['auxiliary']['pv'] + accounts['cash']['balances'][ccy2]
      self.liqDict[ccy] = accounts['fi_' + ccy2 + 'usd']['triggerEstimates']['mm'] / self.spotDict[ccy]
    self.calcSpotDeltaUSD()
    #####
    for ccy in self.validCcys:
      ccy2 = 'xbt' if ccy == 'BTC' else ccy.lower()
      bal = accounts['fi_' + ccy2 + 'usd']['balances']
      symbol = 'pi_' + ccy2 + 'usd'
      if symbol in bal:
        self.futures.loc[ccy, 'FutDelta'] = bal[symbol] / self.spotDict[ccy]
    self.calcFuturesDeltaUSD()
    #####
    pmts,self.oneDayIncome,self.prevIncome=getPayments()
    self.oneDayAnnRet = self.oneDayIncome * 365 / self.futNotional
    self.prevAnnRet = self.prevIncome * 6 * 365 / self.futNotional
    #####
    self.nav = self.spots['SpotDeltaUSD'].sum()
    #####
    for ccy in self.validCcys:
      oneDayFunding = 0
      prevFunding = 0
      if not pmts is None:
        df = pmts.loc[pmts['Ccy'] == ccy, 'rate']
        if len(df) > 0:
          oneDayFunding = df.mean() * 3 * 365
          prevFunding = df[df.index[-1]].mean() * 3 * 365
      estFunding = cl.kfGetEstFunding1(self.api, ccy)
      estFunding2 = cl.kfGetEstFunding2(self.api, ccy)
      self.makeFundingStr(ccy, oneDayFunding, prevFunding, estFunding, estFunding2)
    #####
    self.makeIncomesStr()
    self.isDone = True

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
    openPos=self.api.private_post_openpositions()['result']
    if len(openPos)==0:
      self.mdbUSD=0 # Margin Delta BTC in USD
      self.oneDayIncome = 0
      self.oneDayAnnRet = 0
    else:
      positions = pd.DataFrame(openPos).transpose().set_index('pair')
      if not all([z == 'XXBTZUSD' for z in positions.index]):
        print('Invalid Kraken pair detected!')
        sys.exit(1)
      cl.dfSetFloat(positions, ['vol', 'vol_closed', 'time'])
      positions['date'] = [datetime.datetime.fromtimestamp(int(ts)) for ts in positions['time']]
      positions['volNetBTC'] = positions['vol'] - positions['vol_closed']
      positions['volNetUSD'] = positions['volNetBTC'] * self.spotDict['BTC']
      self.spots.loc['BTC','SpotDelta'] += positions['volNetBTC'].sum()
      self.mdbUSD=positions['volNetUSD'].sum()
      notional = positions['volNetUSD'].abs().sum()
      #####
      self.oneDayIncome = -self.mdbUSD * 0.0006
      self.oneDayAnnRet = self.oneDayIncome * 365 / notional
    #####
    self.calcSpotDeltaUSD()
    tradeBal = self.api.private_post_tradebalance()['result']
    self.nav = float(tradeBal['eb'])+float(tradeBal['n'])
    #####
    freeMargin = float(tradeBal['mf'])
    if self.spots.loc['BTC', 'SpotDeltaUSD'] == 0:
      self.liqBTC = 0
    else:
      self.liqBTC = 1 - freeMargin / self.spots.loc['BTC','SpotDeltaUSD']
    self.isDone = True

  def krPrintBorrow(self, nav):
    liqStr = colored(fmtLiq(self.liqBTC).rjust(5), 'red')
    zPctNAV = '(' + str(round(-self.mdbUSD / nav * 100)) + '%)'
    z1List=[]
    z2List=[]
    for ccy in CR_KR_CCY_DICT.keys():
      n = self.spots.loc[ccy,'SpotDeltaUSD']
      if n>=500: # Strip out small quantities
        z1List.append(ccy)
        z2List.append('$'+str(round(n/1000))+'K')
    if len(z1List)==0 and len(z2List)==0:
      suffix=''
    else:
      suffix='(spot delta '+'/'.join(z1List)+': '
      suffix+='/'.join(z2List)
      suffix+='; XXBTZUSD: $'
      suffix += str(round(self.mdbUSD / 1000)) + 'K)'
    print(liqStr+('KR' + str(self.n) + ' USD est borrow rate: ').rjust(32) + ('22% p.a. ($' + str(round(-self.mdbUSD/1000)) + 'K) '+zPctNAV).ljust(27)+suffix)

####################################################################################################

if __name__ == '__main__':
  ######
  # Init
  ######
  cl.printHeader('CryptoReporter')
  if SHARED_EXCH_DICT['kf']==1 and not APOPHIS_IS_IP_WHITELIST:
    print('[WARNING: IP is not whitelisted for Apophis, therefore KF incomes are not shown]\n')
  _, ftxCore, bbCore, bbtCore, bnCore, bntCore, kfCore, krCores, spotDict, objs = getCores()

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
  nav+= extCoinsNAV + extUSDTNAV
  oneDayIncome+=ftxCore.oneDayFlows+bnCore.oneDayFlows

  ########
  # Output
  ########
  navStrList=[]
  for obj in objs:
    if obj.name!='DUMMY': navStrList.append(getNAVStr(obj.name,obj.nav))
  if extCoinsNAV!=0: navStrList.append(getNAVStr('Ext Coins', extCoinsNAV))
  print(colored(('NAV as of '+cl.getCurrentTime()+': $').rjust(38)+str(round(nav))+' ('+' / '.join(navStrList)+')','blue'))
  #####
  zList=[]
  for ccy in CR_QUOTE_CCY_DICT.keys():
    zList.append(ccy + '=' + str(round(spotDict[ccy], CR_QUOTE_CCY_DICT[ccy])))
  print(colored('24h income: $'.rjust(38)+(str(round(oneDayIncome))+' ('+str(round(oneDayIncome*365/nav*100))+'% p.a.)').ljust(26),'blue')+' / '.join(zList))
  print()
  #####
  for ccy in CR_AG_CCY_DICT.keys():
    printDeltas(ccy,spotDict,agDf.loc[ccy,'SpotDelta'],agDf.loc[ccy,'FutDelta'])
  usdtCores=[]
  if SHARED_EXCH_DICT['bbt']==1: usdtCores.append(bbtCore)
  if SHARED_EXCH_DICT['bnt'] == 1: usdtCores.append(bntCore)
  printUSDTDeltas(ftxCore, bnCore, spotDict, usdtCores)
  print()
  #####
  printFlows(ftxCore, bnCore, nav)
  #####
  printAllDual(ftxCore, kfCore)
  printAllDual(bbtCore, bbCore)
  printAllDual(bntCore, bnCore)
  if SHARED_EXCH_DICT['kr']>0: krPrintAll(krCores, nav)
  #####
  if '-f' in sys.argv:
    while True:
      time.sleep(1)