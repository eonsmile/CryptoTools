################
# Crypto Library
################
from CryptoParams import *
from joblib import Parallel, delayed
import pandas as pd
import numpy as np
import datetime
import sys
import time
import operator
import termcolor
import traceback
import ccxt
import apophis
from retrying import retry

#########
# Classes
#########
class getPrices:
  def __init__(self, exch, api, ccy):
    self.exch = exch
    self.api = api
    self.ccy = ccy

  def run(self):
    if self.exch == 'ftx':
      self.spot = ftxGetMid(self.api, self.ccy+'/USD')      
      self.fut = ftxGetMid(self.api, self.ccy+'-PERP')
      self.spotUSDT = ftxGetMid(self.api, 'USDT/USD')
    elif self.exch == 'bb':
      self.fut=bbGetMid(self.api,self.ccy)
    elif self.exch == 'bbt':
      self.fut=bbtGetMid(self.api,self.ccy)
    elif self.exch == 'bn':
      self.fut = bnGetMid(self.api,self.ccy)
    elif self.exch == 'bnt':
      self.fut = bntGetMid(self.api,self.ccy)
    elif self.exch == 'kf':
      self.kfTickers = kfGetTickers(self.api)
      self.fut = kfGetMid(self.kfTickers,self.ccy)

#####################################################################################################################################

###########
# Functions
###########
###########
# API Inits
###########
def ftxCCXTInit():
  return ccxt.ftx({'apiKey': API_KEY_FTX, 'secret': API_SECRET_FTX, 'enableRateLimit': True, 'nonce': lambda: ccxt.Exchange.milliseconds()})

def bbCCXTInit():
  api = ccxt.bybit({'apiKey': API_KEY_BB, 'secret': API_SECRET_BB, 'enableRateLimit': True, 'nonce': lambda: ccxt.Exchange.milliseconds()})
  api.options['recvWindow']=50000
  return api

def bnCCXTInit():
  api = ccxt.binance({'apiKey': API_KEY_BN, 'secret': API_SECRET_BN, 'enableRateLimit': True, 'nonce': lambda: ccxt.Exchange.milliseconds()})
  api.options['recvWindow']=50000
  return api

def kfApophisInit():
  return apophis.Apophis(API_KEY_KF,API_SECRET_KF,True)

def krCCXTInit(n=1):
  return ccxt.kraken({'apiKey': globals()['API_KEY_KR'+str(n)], 'secret': globals()['API_SECRET_KR'+str(n)], 'enableRateLimit': False})

########
# Prices
########
@retry(wait_fixed=1000)
def ftxGetMid(ftx, name):
  d=ftx.public_get_markets_market_name({'market_name': name})['result']
  return (float(d['bid'])+float(d['ask']))/2

@retry(wait_fixed=1000)
def ftxGetBid(ftx,ticker):
  return float(ftx.public_get_markets_market_name({'market_name':ticker})['result']['bid'])
  
@retry(wait_fixed=1000)
def ftxGetAsk(ftx,ticker):
  return float(ftx.public_get_markets_market_name({'market_name':ticker})['result']['ask'])

@retry(wait_fixed=1000)
def ftxGetFuture(ftx,ccy):
  return ftx.public_get_futures_future_name({'future_name':ccy+'-PERP'})['result']

@retry(wait_fixed=1000)
def bbGetMid(bb, ccy):
  d = bb.v2PublicGetTickers({'symbol': ccy + 'USD'})['result'][0]
  return (float(d['bid_price']) + float(d['ask_price'])) / 2

@retry(wait_fixed=1000)
def bbGetBid(bb,ccy):
  return float(bb.v2PublicGetTickers({'symbol': ccy + 'USD'})['result'][0]['bid_price'])

@retry(wait_fixed=1000)
def bbGetAsk(bb,ccy):
  return float(bb.v2PublicGetTickers({'symbol': ccy + 'USD'})['result'][0]['ask_price'])

@retry(wait_fixed=1000)
def bbtGetMid(bb, ccy):
  d = bb.v2PublicGetTickers({'symbol': ccy + 'USDT'})['result'][0]
  return (float(d['bid_price']) + float(d['ask_price'])) / 2

@retry(wait_fixed=1000)
def bbtGetBid(bb,ccy):
  return float(bb.v2PublicGetTickers({'symbol': ccy + 'USDT'})['result'][0]['bid_price'])

@retry(wait_fixed=1000)
def bbtGetAsk(bb,ccy):
  return float(bb.v2PublicGetTickers({'symbol': ccy + 'USDT'})['result'][0]['ask_price'])

@retry(wait_fixed=1000)
def bnGetMid(bn, ccy):
  d=bn.dapiPublicGetTickerBookTicker({'symbol':ccy+'USD_PERP'})[0]
  return (float(d['bidPrice']) + float(d['askPrice'])) / 2

@retry(wait_fixed=1000)
def bnGetBid(bn, ccy):
  return float(bn.dapiPublicGetTickerBookTicker({'symbol': ccy+'USD_PERP'})[0]['bidPrice'])

@retry(wait_fixed=1000)
def bnGetAsk(bn, ccy):
  return float(bn.dapiPublicGetTickerBookTicker({'symbol': ccy+'USD_PERP'})[0]['askPrice'])

@retry(wait_fixed=1000)
def bntGetMid(bn, ccy):
  d = bn.fapiPublic_get_ticker_bookticker({'symbol': ccy + 'USDT'})
  return (float(d['bidPrice']) + float(d['askPrice'])) / 2

@retry(wait_fixed=1000)
def bntGetBid(bn, ccy):
  return float(bn.fapiPublic_get_ticker_bookticker({'symbol': ccy + 'USDT'})['bidPrice'])

@retry(wait_fixed=1000)
def bntGetAsk(bn, ccy):
  return float(bn.fapiPublic_get_ticker_bookticker({'symbol': ccy + 'USDT'})['askPrice'])

# Do not use @retry
def kfGetMid(kfTickers, ccy):
  ticker=kfCcyToSymbol(ccy)
  return (kfTickers.loc[ticker, 'bid'] + kfTickers.loc[ticker, 'ask']) / 2

# Do not use @retry
def kfGetBid(kf, ccy):
  return kfGetTickers(kf).loc[kfCcyToSymbol(ccy), 'bid']

# Do not use @retry
def kfGetAsk(kf, ccy):
  return kfGetTickers(kf).loc[kfCcyToSymbol(ccy), 'ask']

def getLimitPrice(exch,price,ccy,side):
  if exch == 'ftx':
    distanceToBestBps = CT_CONFIGS_DICT['FTX_DISTANCE_TO_BEST_BPS']
  elif exch == 'bb':
    distanceToBestBps = CT_CONFIGS_DICT['BB_DISTANCE_TO_BEST_BPS']
  elif exch == 'bbt':
    distanceToBestBps = CT_CONFIGS_DICT['BBT_DISTANCE_TO_BEST_BPS']
  elif exch == 'bn':
    distanceToBestBps = CT_CONFIGS_DICT['BN_DISTANCE_TO_BEST_BPS']
  elif exch == 'bnt':
    distanceToBestBps = CT_CONFIGS_DICT['BNT_DISTANCE_TO_BEST_BPS']
  elif exch == 'kf':
    distanceToBestBps = CT_CONFIGS_DICT['KF_DISTANCE_TO_BEST_BPS']
  else:
    sys.exit(1)
  if side == 'BUY':
    mult = 1 + distanceToBestBps / 10000
  else:
    mult = 1 - distanceToBestBps / 10000
  return roundPrice(exch, price * mult, ccy)

def roundPrice(exch, price, ccy):
  method, param = CT_CONFIGS_DICT['ROUND_PRICE_'+exch.upper()].get(ccy, [0, 6])
  if method == 0:
    return round(price, param)
  else:
    return round(price * param) / param

def roundQty(exch, qty, ccy):
  if exch=='ftx':
    return round(qty,CT_CONFIGS_DICT['ROUND_QTY_FTX'].get(ccy, 6))
  elif exch=='bnt':
    return round(qty,CT_CONFIGS_DICT['ROUND_QTY_BNT'].get(ccy, 3))
  else:
    sys.exit(1)

#############################################################################################

#####
# FTX
#####
@retry(wait_fixed=1000)
def ftxGetWallet(ftx):
  wallet = pd.DataFrame(ftx.private_get_wallet_all_balances()['result']['main']).set_index('coin')
  dfSetFloat(wallet,wallet.columns)
  return wallet

@retry(wait_fixed=1000)
def ftxGetFutPos(ftx,ccy):
  df = pd.DataFrame(ftx.private_get_account()['result']['positions']).set_index('future')
  s=df.loc[ccy+'-PERP']
  pos=float(s['size'])
  if s['side']=='sell':
    pos*=-1
  return pos

@retry(wait_fixed=1000)
def ftxGetEstFunding(ftx, ccy):
  return float(ftx.public_get_futures_future_name_stats({'future_name': ccy+'-PERP'})['result']['nextFundingRate']) * 24 * 365

@retry(wait_fixed=1000)
def ftxGetEstBorrow(ftx, ccy=None):
  s=pd.DataFrame(ftx.private_get_spot_margin_borrow_rates()['result']).set_index('coin')['estimate'].astype(float)*24*365
  if ccy is None:
    return s
  else:
    return s[ccy]

@retry(wait_fixed=1000)
def ftxGetEstLending(ftx, ccy=None):
  s=pd.DataFrame(ftx.private_get_spot_margin_lending_rates()['result']).set_index('coin')['estimate'].astype(float) * 24 * 365
  if ccy is None:
    return s
  else:
    return s[ccy]

def ftxRelOrder(side,ftx,ticker,trade_qty,maxChases=0):
  @retry(wait_fixed=1000)
  def ftxGetRemainingSize(ftx,orderId):
    return float(ftx.private_get_orders_order_id({'order_id': orderId})['result']['remainingSize'])
  @retry(wait_fixed=1000)
  def ftxGetFilledSize(ftx, orderId):
    return float(ftx.private_get_orders_order_id({'order_id': orderId})['result']['filledSize'])
  @retry(wait_fixed=1000)
  def ftxGetFillPrice(ftx,orderId):
    return float(ftx.private_get_orders_order_id({'order_id': orderId})['result']['avgFillPrice'])
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  if '/' in ticker:
    ccy=ticker.split('/')[0]
  elif '-' in ticker:
    ccy=ticker.split('-')[0]
  else:
    sys.exit(1)
  qty=roundQty('ftx',trade_qty,ccy)
  print(getCurrentTime()+': Sending FTX '+side+' order of '+ticker+' (qty='+str(qty)+') ....')
  if side == 'BUY':
    refPrice = ftxGetBid(ftx, ticker)
  else:
    refPrice = ftxGetAsk(ftx, ticker)
  limitPrice = getLimitPrice('ftx',refPrice,ccy,side)
  #####
  isOk=False
  for i in range(3):
    try:
      orderId = ftx.private_post_orders({'market': ticker, 'side': side.lower(), 'price': limitPrice, 'type': 'limit', 'size': qty})['result']['id']
      isOk=True
      break
    except ccxt.RateLimitExceeded:
      print(getCurrentTime()+': FTX rate limit exceeded!')
      time.sleep(3)
    except:
      print(traceback.print_exc())
      sys.exit(1)
  if not isOk:
    sys.exit(1)
  #####
  refTime = time.time()
  nChases=0
  while True:
    if ftxGetRemainingSize(ftx,orderId) == 0:
      break
    if side=='BUY':
      newRefPrice=ftxGetBid(ftx,ticker)
    else:
      newRefPrice=ftxGetAsk(ftx,ticker)
    if (side=='BUY' and newRefPrice > refPrice) or (side=='SELL' and newRefPrice < refPrice) or ((time.time()-refTime)>CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice=newRefPrice
      nChases+=1
      if nChases>maxChases and ftxGetRemainingSize(ftx,orderId)==qty:
        mult=.95 if side == 'BUY' else 1.05
        farPrice = roundPrice('ftx', refPrice * mult,ccy)
        try:
          orderId = ftx.private_post_orders_order_id_modify({'order_id': orderId, 'price': farPrice})['result']['id']
        except:
          break
        if ftxGetRemainingSize(ftx, orderId) == qty:
          ftx.private_delete_orders_order_id({'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        refTime=time.time()
        newLimitPrice=getLimitPrice('ftx',refPrice,ccy,side)
        if (side=='BUY' and newLimitPrice > limitPrice) or (side=='SELL' and newLimitPrice < limitPrice):
          limitPrice=newLimitPrice
          try:
            orderId=ftx.private_post_orders_order_id_modify({'order_id':orderId,'price':limitPrice})['result']['id']
          except:
            break
    time.sleep(1)
  fill=ftxGetFillPrice(ftx,orderId)
  print(getCurrentTime() + ': Filled at '+str(round(fill,6)))
  return fill

#############################################################################################

####
# BB
####
@retry(wait_fixed=1000)
def bbGetFutPos(bb,ccy):
  df = bb.v2_private_get_position_list()['result']
  df = pd.DataFrame([pos['data'] for pos in df]).set_index('symbol')
  s=df.loc[ccy+'USD']
  pos = float(s['size'])
  if s['side'] == 'Sell':
    pos *= -1
  return pos

@retry(wait_fixed=1000)
def bbGetEstFunding1(bb,ccy):
  return float(bb.v2PrivateGetFundingPrevFundingRate({'symbol': ccy+'USD'})['result']['funding_rate']) * 3 * 365

@retry(wait_fixed=1000)
def bbGetEstFunding2(bb, ccy):
  return float(bb.v2PrivateGetFundingPredictedFunding({'symbol': ccy+'USD'})['result']['predicted_funding_rate']) * 3 * 365

def bbRelOrder(side,bb,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def bbGetOrder(bb,ticker,orderId):
    result=bb.v2_private_get_order({'symbol': ticker, 'order_id': orderId})['result']
    if len(result)==0:
      result=dict()
      result['orderStatus']='Filled'
    return result
  @retry(wait_fixed=1000)
  def bbGetFillPrice(bb, ticker, orderId):
    df = pd.DataFrame(bb.v2_private_get_execution_list({'symbol': ticker, 'order_id': orderId})['result']['trade_list'])
    df['exec_qty'] = [float(n) for n in df['exec_qty']]
    df['exec_price'] = [float(n) for n in df['exec_price']]
    return (df['exec_qty'] * df['exec_price']).sum() / df['exec_qty'].sum()
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  ticker=ccy+'USD'
  trade_notional = round(trade_notional)
  print(getCurrentTime() + ': Sending BB ' + side + ' order of ' + ticker + ' (notional=$'+ str(trade_notional)+') ....')
  if side=='BUY':
    refPrice = bbGetBid(bb, ccy)
    limitPrice=getLimitPrice('bb',refPrice,ccy,side)
    orderId = bb.create_limit_buy_order(ccy+'/USD', trade_notional, limitPrice)['info']['order_id']
  else:
    refPrice = bbGetAsk(bb, ccy)
    limitPrice=getLimitPrice('bb',refPrice,ccy,side)
    orderId = bb.create_limit_sell_order(ccy+'/USD', trade_notional, limitPrice)['info']['order_id']
  print(getCurrentTime() + ': [DEBUG: orderId=' + orderId + '; price=' + str(limitPrice) + '] ')
  refTime = time.time()
  nChases=0
  while True:
    orderStatus=bbGetOrder(bb,ticker,orderId)
    if orderStatus['order_status']=='Filled': break
    if side=='BUY':
      newRefPrice=bbGetBid(bb,ccy)
    else:
      newRefPrice=bbGetAsk(bb,ccy)
    if (side=='BUY' and newRefPrice > refPrice) or (side=='SELL' and newRefPrice < refPrice) or ((time.time()-refTime)>CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice = newRefPrice
      nChases+=1
      orderStatus = bbGetOrder(bb, ticker, orderId)
      if orderStatus['order_status']=='Filled': break
      if nChases>maxChases and float(orderStatus['cum_exec_qty'])==0:
        mult = .95 if side == 'BUY' else 1.05
        farPrice = roundPrice('bb',refPrice*mult,ccy)
        try:
          bb.v2_private_post_order_replace({'symbol':ticker,'order_id':orderId, 'p_r_price': farPrice})
        except:
          break
        orderStatus = bbGetOrder(bb, ticker, orderId)
        if float(orderStatus['cum_exec_qty']) == 0:
          bb.v2_private_post_order_cancel({'symbol': ticker, 'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        refTime = time.time()
        newLimitPrice=getLimitPrice('bb',refPrice,ccy,side)
        if (side == 'BUY' and newLimitPrice > limitPrice) or (side == 'SELL' and newLimitPrice < limitPrice):
          print(getCurrentTime() + ': [DEBUG: replace order; nChases=' + str(nChases) + '; price=' + str(limitPrice) + '->' + str(newLimitPrice) + ']')
          limitPrice=newLimitPrice
          try:
            bb.v2_private_post_order_replace({'symbol':ticker,'order_id':orderId, 'p_r_price': limitPrice})
          except:
            break
        else:
          print(getCurrentTime() + ': [DEBUG: leave order alone; nChases=' + str(nChases)+'; price='+str(limitPrice)+']')
    time.sleep(1)
  fill=bbGetFillPrice(bb, ticker, orderId)
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

#####
# BBT
#####
@retry(wait_fixed=1000)
def bbtGetFutPos(bb,ccy):
  df=pd.DataFrame(bb.private_linear_get_position_list({'symbol':ccy+'USDT'})['result']).set_index('side')
  return float(df.loc['Buy','size'])-float(df.loc['Sell','size'])

@retry(wait_fixed=1000)
def bbtGetEstFunding1(bb,ccy):
  return float(bb.public_linear_get_funding_prev_funding_rate({'symbol': ccy+'USDT'})['result']['funding_rate'])*3*365

@retry(wait_fixed=1000)
def bbtGetEstFunding2(bb,ccy):
  return float(bb.private_linear_get_funding_predicted_funding({'symbol': ccy+'USDT'})['result']['predicted_funding_rate'])* 3 * 365

@retry(wait_fixed=1000)
def bbtGetRiskDf(bb,ccys,spotDict):
  # Get dictionaries of risk_id -> im/mm
  imDict = dict()
  mmDict = dict()
  for ccy in ccys:
    riskLimit=bb.public_linear_get_risk_limit({'symbol': ccy + 'USDT'})['result']
    for i in range(len(riskLimit)):
      imDict[riskLimit[i]['id']]=float(riskLimit[i]['starting_margin'])
      mmDict[riskLimit[i]['id']]=float(riskLimit[i]['maintain_margin'])

  # Set up risk df
  positionList = bb.private_linear_get_position_list()['result']
  positionList = pd.DataFrame([pos['data'] for pos in positionList]).set_index('symbol')
  dfSetFloat(positionList, ['size', 'position_value', 'liq_price','unrealised_pnl'])
  df=pd.DataFrame()
  for ccy in ccys:
    tmp=positionList.loc[ccy + 'USDT'].set_index('side')
    position_value = tmp.loc['Buy', 'position_value'] - tmp.loc['Sell', 'position_value']
    unrealised_pnl = tmp['unrealised_pnl'].sum()
    dominantSide='Buy' if tmp.loc['Buy', 'size'] >= tmp.loc['Sell', 'size'] else 'Sell'
    spot_price = spotDict[ccy]/spotDict['USDT']
    liq_price = tmp.loc[dominantSide, 'liq_price']
    liq = liq_price / spot_price
    im = imDict[tmp.loc[dominantSide, 'risk_id']]
    mm = mmDict[tmp.loc[dominantSide, 'risk_id']]
    df=df.append({'ccy':ccy,
                    'position_value':position_value,
                    'spot_price':spot_price,
                    'liq_price':liq_price,
                    'liq':liq,
                    'unrealised_pnl':unrealised_pnl,
                    'im':im,
                    'mm': mm}, ignore_index=True)
  df=df.set_index('ccy')
  df['im_value']=(df['position_value']*df['im']).abs()
  df['mm_value']=(df['position_value']*df['mm']).abs()
  df['delta_value']=df['position_value']+df['unrealised_pnl']
  return df[['position_value','delta_value','spot_price','liq_price','liq','unrealised_pnl','im','mm','im_value','mm_value']]

def bbtRelOrder(side,bb,ccy,trade_qty,maxChases=0):
  # Do not use @retry
  def getIsReduceOnly(bb, ccy, side, qty, cushionUSD=30000):
    df = pd.DataFrame(bb.private_linear_get_position_list({'symbol': ccy + 'USDT'})['result']).set_index('side')
    oppSide = 'Sell' if side == 'BUY' else 'Buy'
    return (qty + cushionUSD / bbtGetMid(bb, ccy)) < float(df.loc[oppSide, 'size'])
  @retry(wait_fixed=1000)
  def bbtGetOrder(bb,ticker,orderId):
    isEllipsisShown=False
    while True:
      result=bb.private_linear_get_order_list({'symbol': ticker, 'order_id': orderId})['result']['data']
      if result is None:
        print('.', end='')
        isEllipsisShown = True
        time.sleep(1)
      else:
        if isEllipsisShown: print()
        return result[0]
  @retry(wait_fixed=1000)
  def bbtGetFillPrice(bb, ticker, orderId):
    while True:
      df = pd.DataFrame(bb.private_linear_get_trade_execution_list({'symbol': ticker})['result']['data'])
      df = df[df['order_id'] == orderId]
      dfSetFloat(df, ['exec_qty', 'exec_price'])
      exec_qty_sum = df['exec_qty'].sum()
      print(getCurrentTime() + ': [DEBUG: exec_qty_sum: ' + str(round(exec_qty_sum, 6)) + ']')
      if exec_qty_sum > 0:
        return (df['exec_qty'] * df['exec_price']).sum() / exec_qty_sum
      time.sleep(1)
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  ticker=ccy+'USDT'
  qty = round(trade_qty, 3)
  print(getCurrentTime() + ': Sending BBT ' + side + ' order of ' + ticker + ' (qty='+ str(qty)+') ....')
  if side=='BUY':
    refPrice = bbtGetBid(bb, ccy)
  else:
    refPrice = bbtGetAsk(bb, ccy)
  limitPrice=getLimitPrice('bbt',refPrice,ccy,side)
  isReduceOnly=getIsReduceOnly(bb, ccy, side, qty)
  orderId=bb.private_linear_post_order_create({'side':side.capitalize(),'symbol':ticker,'order_type':'Limit','qty':qty,'price':limitPrice,'time_in_force':'GoodTillCancel',
                                               'reduce_only':bool(isReduceOnly),'close_on_trigger':False})['result']['order_id']
  print(getCurrentTime() + ': [DEBUG: orderId=' + orderId + '; price=' + str(limitPrice) + '] ', end='')
  refTime = time.time()
  nChases=0
  while True:
    orderStatus=bbtGetOrder(bb,ticker,orderId)
    if orderStatus['order_status']=='Filled': break
    if side=='BUY':
      newRefPrice=bbtGetBid(bb,ccy)
    else:
      newRefPrice=bbtGetAsk(bb,ccy)
    if (side=='BUY' and newRefPrice > refPrice) or (side=='SELL' and newRefPrice < refPrice) or ((time.time()-refTime)>CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice = newRefPrice
      nChases+=1
      orderStatus = bbtGetOrder(bb, ticker, orderId)
      if orderStatus['order_status']=='Filled': break
      if nChases>maxChases and float(orderStatus['cum_exec_qty'])==0:
        mult = .95 if side == 'BUY' else 1.05
        farPrice = roundPrice('bbt',refPrice*mult,ccy)
        try:
          bb.private_linear_post_order_replace({'symbol':ticker,'order_id':orderId, 'p_r_price': farPrice})
        except:
          break
        orderStatus = bbtGetOrder(bb, ticker, orderId)
        if float(orderStatus['cum_exec_qty']) == 0:
          bb.private_linear_post_order_cancel({'symbol': ticker, 'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        refTime = time.time()
        newLimitPrice=getLimitPrice('bbt',refPrice,ccy,side)
        if (side == 'BUY' and newLimitPrice > limitPrice) or (side == 'SELL' and newLimitPrice < limitPrice):
          print(getCurrentTime() + ': [DEBUG: replace order; nChases=' + str(nChases) + '; price=' + str(limitPrice)+'->'+str(newLimitPrice) + ']')
          limitPrice=newLimitPrice
          try:
            bb.private_linear_post_order_replace({'symbol':ticker,'order_id':orderId, 'p_r_price': limitPrice})
          except:
            break
        else:
          print(getCurrentTime() + ': [DEBUG: leave order alone; nChases=' + str(nChases) + '; price=' + str(limitPrice) + ']')
    time.sleep(1)
  fill=bbtGetFillPrice(bb, ticker, orderId)
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

####
# BN
####
@retry(wait_fixed=1000)
def bnGetFutPos(bn,ccy):
  return float(pd.DataFrame(bn.dapiPrivate_get_positionrisk({'pair':ccy+'USD'})).set_index('symbol').loc[ccy + 'USD_PERP']['positionAmt'])

@retry(wait_fixed=1000)
def bnGetEstFunding(bn, ccy):
  return float(bn.dapiPublic_get_premiumindex({'symbol': ccy + 'USD_PERP'})[0]['lastFundingRate'])*3*365

@retry(wait_fixed=1000)
def bnGetIsolatedMarginDf(bn,spotDict):
  def getYest():
    return int((datetime.datetime.timestamp(datetime.datetime.now() - pd.DateOffset(days=1))))
  #####
  df=pd.DataFrame()
  for i in bn.sapi_get_margin_isolated_account()['assets']:
    qty=float(i['baseAsset']['netAsset'])
    if qty!=0:
      symbol = i['symbol']
      symbolAsset = i['baseAsset']['asset']
      symbolColl=i['quoteAsset']['asset']
      qtyColl = float(i['quoteAsset']['totalAsset'])
      if symbolColl== 'BTC':
        qtyBTC = qtyColl
        qtyUSDT = 0
      elif symbolColl== 'USDT':
        qtyBTC = 0
        qtyUSDT = qtyColl
      else:
        sys.exit(1)
      liq = float(i['liquidatePrice']) / float(i['indexPrice'])
      #############
      df2 = pd.DataFrame(bn.sapi_get_margin_interesthistory({'isolatedSymbol': symbol, 'size': 100, 'startTime': getYest() * 1000})['rows'])
      dfSetFloat(df2, ['interestAccuredTime','principal','interest','interestRate'])
      df2['date'] = [datetime.datetime.fromtimestamp(int(ts) / 1000) for ts in df2['interestAccuredTime']]
      df2 = df2.set_index('date').sort_index()
      principal = df2['principal'][-1] * spotDict[symbolAsset]
      oneDayFlows = -df2['interest'].sum() * spotDict[symbolAsset]
      oneDayFlowsAnnRet = oneDayFlows * 365 / principal
      prevFlows = -df2['interest'][-1] * spotDict[symbolAsset]
      prevFlowsAnnRet = prevFlows * 24 * 365 / principal
      #############
      df=df.append({'symbol':symbol,
                    'symbolAsset':symbolAsset,
                    'symbolColl':symbolColl,
                    'qty':qty,
                    'collateralBTC':qtyBTC,
                    'collateralUSDT':qtyUSDT,
                    'liq':liq,
                    'oneDayFlows':oneDayFlows,
                    'oneDayFlowsAnnRet':oneDayFlowsAnnRet,
                    'prevFlows':prevFlows,
                    'prevFlowsAnnRet':prevFlowsAnnRet}, ignore_index=True)
  df=df[['symbol','symbolAsset','symbolColl','qty','collateralBTC','collateralUSDT','liq','oneDayFlows','oneDayFlowsAnnRet','prevFlows','prevFlowsAnnRet']].set_index('symbol')
  return df

def bnRelOrder(side,bn,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def bnGetOrder(bn, ticker, orderId):
    return bn.dapiPrivate_get_order({'symbol': ticker, 'orderId': orderId})
  # Do not use @retry
  def bnPlaceOrder(bn, ticker, side, qty, limitPrice):
    return bn.dapiPrivate_post_order({'symbol': ticker, 'side': side, 'type': 'LIMIT', 'quantity': qty, 'price': limitPrice, 'timeInForce': 'GTC'})['orderId']
  # Do not use @retry
  def bnCancelOrder(bn, ticker, orderId):
    try:
      orderStatus=bn.dapiPrivate_delete_order({'symbol': ticker, 'orderId': orderId})
      if orderStatus['status']!='CANCELED':
        print('Order cancellation failed!')
        sys.exit(1)
      return orderStatus,float(orderStatus['origQty'])-float(orderStatus['executedQty'])
    except:
      orderStatus=bnGetOrder(bn, ticker, orderId)
      return orderStatus,0
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  ticker=ccy+'USD_PERP'
  print(getCurrentTime() + ': Sending BN ' + side + ' order of ' + ticker + ' (notional=$'+ str(round(trade_notional))+') ....')
  if ccy=='BTC':
    qty=round(trade_notional/100)
  elif ccy in ['ETH','XRP','BNB']:
    qty=round(trade_notional/10)
  else:
    sys.exit(1)
  if side == 'BUY':
    refPrice = bnGetBid(bn, ccy)
  else:
    refPrice = bnGetAsk(bn, ccy)
  limitPrice = getLimitPrice('bn', refPrice, ccy, side)
  orderId=bnPlaceOrder(bn, ticker, side, qty, limitPrice)
  refTime = time.time()
  nChases=0
  while True:
    orderStatus = bnGetOrder(bn, ticker, orderId)
    if orderStatus['status']=='FILLED':
      break
    if side=='BUY':
      newRefPrice=bnGetBid(bn,ccy)
    else:
      newRefPrice=bnGetAsk(bn,ccy)
    if (side == 'BUY' and newRefPrice > refPrice) or (side == 'SELL' and newRefPrice < refPrice) or ((time.time() - refTime) > CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice=newRefPrice
      nChases+=1
      orderStatus,leavesQty=bnCancelOrder(bn,ticker,orderId)
      if nChases>maxChases and leavesQty==qty:
        print(getCurrentTime() + ': Cancelled')
        return 0
      elif leavesQty==0:
        break
      else:
        refTime = time.time()
        limitPrice = getLimitPrice('bn', refPrice, ccy, side)
        orderId=bnPlaceOrder(bn, ticker, side, leavesQty, limitPrice)
    time.sleep(1)
  fill=float(orderStatus['avgPrice'])
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

#####
# BNT
#####
@retry(wait_fixed=1000)
def bntGetFutPos(bn, ccy):
  return float(bn.fapiPrivate_get_positionrisk({'symbol':ccy+'USDT'})[0]['positionAmt'])

@retry(wait_fixed=1000)
def bntGetEstFunding(bn, ccy):
  return float(bn.fapiPublic_get_premiumindex({'symbol': ccy + 'USDT'})['lastFundingRate']) * 3 * 365

@retry(wait_fixed=1000)
def bntGetRiskDf(bn,ccys):
  positionRisk = pd.DataFrame(bn.fapiPrivate_get_positionrisk()).set_index('symbol').loc[[z + 'USDT' for z in ccys]]
  cols = ['positionAmt','entryPrice','markPrice','unRealizedProfit','liquidationPrice','notional']
  df=positionRisk[cols].copy()
  dfSetFloat(df,cols)
  df['liq'] = df['liquidationPrice'] / df['markPrice']
  return df

def bntRelOrder(side, bn, ccy, trade_qty, maxChases=0):
  @retry(wait_fixed=1000)
  def bntGetOrder(bn, ticker, orderId):
    return bn.fapiPrivate_get_order({'symbol': ticker, 'orderId': orderId})
  # Do not use @retry
  def bntPlaceOrder(bn, ticker, side, qty, limitPrice):
    print(getCurrentTime() + ': [DEBUG: place order; qty=' + str(qty)+' price=' + str(limitPrice) + ']')
    return bn.fapiPrivate_post_order({'symbol': ticker, 'side': side, 'type': 'LIMIT', 'quantity': qty, 'price': limitPrice, 'timeInForce': 'GTC'})['orderId']
  # Do not use @retry
  def bntCancelOrder(bn, ticker, orderId):
    try:
      orderStatus=bn.fapiPrivate_delete_order({'symbol': ticker, 'orderId': orderId})
      if orderStatus['status']!='CANCELED':
        print('Order cancellation failed!')
        sys.exit(1)
      return orderStatus,float(orderStatus['origQty'])-float(orderStatus['executedQty'])
    except:
      orderStatus=bntGetOrder(bn, ticker, orderId)
      return orderStatus,0
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  ticker=ccy+'USDT'
  qty = roundQty('bnt', trade_qty, ccy)
  print(getCurrentTime()+': Sending BNT '+side+' order of '+ticker+' (qty='+str(qty)+') ....')
  if side == 'BUY':
    refPrice = bntGetBid(bn, ccy)
  else:
    refPrice = bntGetAsk(bn, ccy)
  limitPrice = getLimitPrice('bnt', refPrice, ccy, side)
  orderId=bntPlaceOrder(bn, ticker, side, qty, limitPrice)
  refTime = time.time()
  nChases=0
  while True:
    orderStatus = bntGetOrder(bn, ticker, orderId)
    if orderStatus['status']=='FILLED':
      break
    if side=='BUY':
      newRefPrice=bntGetBid(bn,ccy)
    else:
      newRefPrice=bntGetAsk(bn,ccy)
    if (side == 'BUY' and newRefPrice > refPrice) or (side == 'SELL' and newRefPrice < refPrice) or ((time.time() - refTime) > CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice=newRefPrice
      nChases+=1
      orderStatus,leavesQty=bntCancelOrder(bn,ticker,orderId)
      if nChases>maxChases and leavesQty==qty:
        print(getCurrentTime() + ': Cancelled')
        return 0
      elif leavesQty==0:
        break
      else:
        refTime = time.time()
        limitPrice = getLimitPrice('bnt', refPrice, ccy, side)
        orderId=bntPlaceOrder(bn, ticker, side, roundQty('bnt', leavesQty, ccy), limitPrice)
    time.sleep(1)
  fill=float(orderStatus['avgPrice'])
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

####
# KF
####
def kfCcyToSymbol(ccy,isIndex=False):
  suffix ='XBT' if ccy=='BTC' else ccy
  suffix = '_'+suffix.lower()+'usd'
  if isIndex:
    return 'in'+suffix
  else:
    return 'pi'+suffix

@retry(wait_fixed=1000)
def kfGetFutPos(kf,ccy):
  symbol=kfCcyToSymbol(ccy)
  return kf.query('accounts')['accounts']['f'+symbol[1:]]['balances'][symbol]

@retry(wait_fixed=1000)
def kfGetTickers(kf):
  return pd.DataFrame(kf.query('tickers')['tickers']).set_index('symbol')

@retry(wait_fixed=1000)
def kfGetEstFunding1(kf,ccy,kfTickers=None):
  if kfTickers is None:
    kfTickers=kfGetTickers(kf)
  symbol=kfCcyToSymbol(ccy)
  return kfTickers.loc[symbol,'fundingRate']*kfTickers.loc[symbol,'markPrice']*24*365

@retry(wait_fixed=1000)
def kfGetEstFunding2(kf, ccy,kfTickers=None):
  if kfTickers is None:
    kfTickers = kfGetTickers(kf)
  symbol = kfCcyToSymbol(ccy)
  return kfTickers.loc[symbol, 'fundingRatePrediction']*kfTickers.loc[symbol,'markPrice']*24*365

def kfRelOrder(side,kf,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def kfGetOrderStatus(kf, orderId):
    l = kf.query('openorders')['openOrders']
    if len(l)==0:
      return None
    else:
      df= pd.DataFrame(l).set_index('order_id')
      if orderId in df.index:
        return df.loc[orderId]
      else:
        return None
  # Do not use @retry
  def kfGetFillPrice(kf, orderId):
    df=pd.DataFrame(kf.query('fills')['fills']).set_index('order_id').loc[orderId]
    if isinstance(df, pd.Series):
      return df['price']
    else:
      df['value']=df['size']*df['price']
      return df['value'].sum()/df['size'].sum()
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  symbol=kfCcyToSymbol(ccy)
  trade_notional = round(trade_notional)
  print(getCurrentTime() + ': Sending KF ' + side + ' order of ' + symbol + ' (notional=$' + str(trade_notional) + ') ....')
  if side == 'BUY':
    refPrice = kfGetBid(kf, ccy)
  else:
    refPrice = kfGetAsk(kf, ccy)
  limitPrice = getLimitPrice('kf', refPrice, ccy, side)
  orderId=kf.query('sendorder',{'orderType':'lmt','symbol':symbol,'side':side.lower(),'size':trade_notional,'limitPrice':limitPrice})['sendStatus']['order_id']
  refTime=time.time()
  nChases=0
  while True:
    orderStatus=kfGetOrderStatus(kf,orderId)
    if orderStatus is None:  # If order doesn't exist, it means all executed
      break
    if side=='BUY':
      newRefPrice=kfGetBid(kf,ccy)
    else:
      newRefPrice=kfGetAsk(kf,ccy)
    if (side=='BUY' and newRefPrice > refPrice) or (side=='SELL' and newRefPrice < refPrice) or ((time.time()-refTime)>CT_CONFIGS_DICT['MAX_WAIT_TIME']):
      refPrice=newRefPrice
      nChases+=1
      orderStatus = kfGetOrderStatus(kf, orderId)
      if orderStatus is None:  # If order doesn't exist, it means all executed
        break
      if nChases>maxChases and float(orderStatus['filledSize'])==0:
        mult = .98 if side == 'BUY' else 1.02
        farPrice = roundPrice('kf', refPrice * mult, ccy)
        try:
          kf.query('editorder',{'orderId':orderId,'limitPrice':farPrice})
        except:
          break
        orderStatus = kfGetOrderStatus(kf, orderId)
        if orderStatus is None:  # If order doesn't exist, it means all executed
          break
        if float(orderStatus['filledSize']) == 0:
          kf.query('cancelorder',{'order_id':orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        refTime=time.time()
        newLimitPrice = getLimitPrice('kf', refPrice, ccy, side)
        if (side=='BUY' and newLimitPrice > limitPrice) or (side=='SELL' and newLimitPrice < limitPrice):
          limitPrice=newLimitPrice
          try:
            kf.query('editorder', {'orderId': orderId, 'limitPrice': limitPrice})
          except:
            break
    time.sleep(1)
  fill=kfGetFillPrice(kf, orderId)
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

####################
# Smart basis models
####################
def getFundingDict(ftx,bb,bn,kf,ccy,isRateLimit=False):
  def getMarginal(ftxWallet,borrowS,lendingS,ccy):
    if ftxWallet.loc[ccy, 'total'] >= 0:
      return lendingS[ccy]
    else:
      return borrowS[ccy]
  #####
  # Common
  ftxWallet = ftxGetWallet(ftx)
  borrowS = ftxGetEstBorrow(ftx)
  lendingS = ftxGetEstLending(ftx)
  d=dict()
  d['ftxEstMarginalUSD'] = getMarginal(ftxWallet,borrowS,lendingS,'USD')
  d['ftxEstMarginalUSDT'] = getMarginal(ftxWallet,borrowS,lendingS,'USDT')
  #####
  # Ccy-specific
  d['Ccy'] = ccy
  validExchs=getValidExchs(ccy)
  if 'ftx' in validExchs: d['ftxEstFunding'] = ftxGetEstFunding(ftx, ccy)
  if 'bb' in validExchs:
    d['bbEstFunding1'] = bbGetEstFunding1(bb, ccy)
    d['bbEstFunding2'] = bbGetEstFunding2(bb, ccy)
  if 'bbt' in validExchs:
    d['bbtEstFunding1'] = bbtGetEstFunding1(bb, ccy)
    d['bbtEstFunding2'] = bbtGetEstFunding2(bb, ccy)
  if 'bn' in validExchs:  d['bnEstFunding'] = bnGetEstFunding(bn, ccy)
  if 'bnt' in validExchs: d['bntEstFunding'] = bntGetEstFunding(bn, ccy)
  if 'kf' in validExchs:
    kfTickers = kfGetTickers(kf)
    d['kfEstFunding1'] = kfGetEstFunding1(kf, ccy, kfTickers)
    d['kfEstFunding2'] = kfGetEstFunding2(kf, ccy, kfTickers)
  if isRateLimit:
    if ccy in ['BTC', 'ETH']:
      time.sleep(1)
    else:
      time.sleep(2)
  return d

#############################################################################################

def getOneDayShortSpotEdge(fundingDict):
  return getOneDayDecayedMean(fundingDict['ftxEstMarginalUSD'], SMB_BASE_RATE, SMB_HALF_LIFE_HOURS) / 365

def getOneDayUSDTCollateralBleed(fundingDict):
  return -getOneDayDecayedMean(fundingDict['ftxEstMarginalUSDT'], SMB_BASE_RATE, SMB_HALF_LIFE_HOURS) / 365 * SMB_USDT_COLLATERAL_COVERAGE

def getOneDayShortFutEdge(hoursInterval,basis,snapFundingRate,estFundingRate,pctElapsedPower=1,prevFundingRate=None,isKF=False):
  # gain on projected basis mtm after 1 day
  edge=basis-getOneDayDecayedValues(basis, SMB_BASE_BASIS, SMB_HALF_LIFE_HOURS)[-1]

  # gain on coupon from previous reset
  hoursAccountedFor=0
  if not prevFundingRate is None:
    if isKF:
      pctToCapture = 1 - getPctElapsed(hoursInterval)
    else:
      pctToCapture = 1
    edge += prevFundingRate / 365 / (24 / hoursInterval) * pctToCapture
    hoursAccountedFor += hoursInterval * pctToCapture

  # gain on coupon from elapsed time; ignore for kf as est unreliable
  if not isKF:
    pctElapsed = getPctElapsed(hoursInterval) ** pctElapsedPower
    edge += estFundingRate / 365 / (24 / hoursInterval) * pctElapsed
    hoursAccountedFor+=hoursInterval*pctElapsed

  # gain on projected funding pickup
  nMinutes = 1440 - round(hoursAccountedFor * 60)
  edge+= getOneDayDecayedMean(snapFundingRate, SMB_BASE_RATE, SMB_HALF_LIFE_HOURS, nMinutes=nMinutes) / 365 * (nMinutes / 1440)

  return edge

#############################################################################################

@retry(wait_fixed=1000)
def ftxGetOneDayShortFutEdge(ftx, fundingDict, basis):
  keySnap='ftxEMASnap'+fundingDict['Ccy']
  if cache('r',keySnap) is None:
    cache('w',keySnap,fundingDict['ftxEstFunding'])
  d=ftxGetFuture(ftx,fundingDict['Ccy'])
  snapFundingRate=(float(d['mark']) / float(d['index']) - 1)*365
  smoothedSnapFundingRate = getEMANow(snapFundingRate, cache('r',keySnap), CT_CONFIGS_DICT['EMA_K'])
  cache('w',keySnap,smoothedSnapFundingRate)
  return getOneDayShortFutEdge(1,basis,smoothedSnapFundingRate, fundingDict['ftxEstFunding'])

@retry(wait_fixed=1000)
def bbGetOneDayShortFutEdge(bb, fundingDict, basis):
  start_time = int((datetime.datetime.timestamp(datetime.datetime.now() - pd.DateOffset(minutes=15))))
  premIndex=np.mean([float(n) for n in pd.DataFrame(bb.v2_public_get_premium_index_kline({'symbol':fundingDict['Ccy']+'USD','interval':'1','from':start_time})['result'])['close']])
  premIndexClamped  = premIndex + np.clip(0.0001 - premIndex, -0.0005, 0.0005)
  snapFundingRate=premIndexClamped*365*3
  return getOneDayShortFutEdge(8, basis, snapFundingRate, fundingDict['bbEstFunding2'], prevFundingRate=fundingDict['bbEstFunding1'])

@retry(wait_fixed=1000)
def bbtGetOneDayShortFutEdge(bb, fundingDict, basis):
  start_time = int((datetime.datetime.timestamp(datetime.datetime.now() - pd.DateOffset(minutes=15))))
  premIndex=np.mean([float(n) for n in pd.DataFrame(bb.public_linear_get_premium_index_kline({'symbol':fundingDict['Ccy']+'USDT','interval':1,'from':start_time})['result'])['close']])
  premIndexClamped  = premIndex + np.clip(0.0001 - premIndex, -0.0005, 0.0005)
  snapFundingRate=premIndexClamped*365*3
  return getOneDayShortFutEdge(8, basis, snapFundingRate, fundingDict['bbtEstFunding2'], prevFundingRate=fundingDict['bbtEstFunding1']) - getOneDayUSDTCollateralBleed(fundingDict)

@retry(wait_fixed=1000)
def bnGetOneDayShortFutEdge(bn, fundingDict, basis):
  df=pd.DataFrame(bn.dapiData_get_basis({'pair': fundingDict['Ccy'] + 'USD', 'contractType': 'PERPETUAL', 'period': '1m'}))[-15:]
  dfSetFloat(df,['basis','indexPrice'])
  premIndex=(df['basis'] / df['indexPrice']).mean()
  premIndexClamped=premIndex+np.clip(0.0001-premIndex,-0.0005,0.0005)
  snapFundingRate=premIndexClamped*365*3
  return getOneDayShortFutEdge(8, basis,snapFundingRate, fundingDict['bnEstFunding'], pctElapsedPower=2)

@retry(wait_fixed=1000)
def bntGetOneDayShortFutEdge(bn, fundingDict, basis):
  keyPremIndex='bntEMAPremIndex'+fundingDict['Ccy']
  if cache('r',keyPremIndex) is None:
    cache('w',keyPremIndex,fundingDict['bntEstFunding'] / 365 / 3)
  d = bn.fapiPublic_get_premiumindex({'symbol': fundingDict['Ccy'] + 'USDT'})
  premIndex = float(d['markPrice']) / float(d['indexPrice']) - 1
  smoothedPremIndex = getEMANow(premIndex, cache('r',keyPremIndex), CT_CONFIGS_DICT['EMA_K'])
  cache('w',keyPremIndex,smoothedPremIndex)
  smoothedSnapFundingRate = (smoothedPremIndex + np.clip(0.0001 - smoothedPremIndex, -0.0005, 0.0005))*365*3
  return getOneDayShortFutEdge(8, basis,smoothedSnapFundingRate, fundingDict['bntEstFunding'], pctElapsedPower=2) - getOneDayUSDTCollateralBleed(fundingDict)

@retry(wait_fixed=1000)
def kfGetOneDayShortFutEdge(kfTickers, fundingDict, basis):
  keySnap='kfEMASnap'+fundingDict['Ccy']
  #keyEst2='kfEMAEst2'+fundingDict['Ccy']
  if cache('r',keySnap) is None:
    cache('w',keySnap,fundingDict['kfEstFunding2'])
  #if cache('r',keyEst2) is None:
  #  cache('w',keyEst2,fundingDict['kfEstFunding2'])
  mid=kfGetMid(kfTickers,fundingDict['Ccy'])
  premIndexClipped = np.clip(mid / kfTickers.loc[kfCcyToSymbol(fundingDict['Ccy'],isIndex=True), 'last'] - 1, -0.008, 0.008)
  snapFundingRate = premIndexClipped * 365 * 3
  smoothedSnapFundingRate = getEMANow(snapFundingRate, cache('r', keySnap), CT_CONFIGS_DICT['EMA_K'])
  cache('w', keySnap, smoothedSnapFundingRate)
  #smoothedEst2Rate = getEMANow(fundingDict['kfEstFunding2'], cache('r', keyEst2), CT_CONFIGS_DICT['EMA_K'])
  #cache('w', keyEst2, smoothedEst2Rate)
  return getOneDayShortFutEdge(4, basis, smoothedSnapFundingRate, None, prevFundingRate=fundingDict['kfEstFunding1'], isKF=True)

#############################################################################################

def getSmartBasisDict(ftx, bb, bn, kf, ccy, fundingDict, isSkipAdj=False):
  validExchs = getValidExchs(ccy)
  objs=[]
  if 'ftx' in validExchs:
    ftxPrices = getPrices('ftx', ftx, ccy)
    objs.append(ftxPrices)
  if 'bbt' in validExchs:
    bbtPrices = getPrices('bbt', bb, ccy)
    objs.append(bbtPrices)
  if 'bnt' in validExchs:
    bntPrices = getPrices('bnt', bn, ccy)
    objs.append(bntPrices)
  if 'bb' in validExchs:
    bbPrices = getPrices('bb', bb, ccy)
    objs.append(bbPrices)
  if 'bn' in validExchs:
    bnPrices = getPrices('bn', bn, ccy)
    objs.append(bnPrices)
  if 'kf' in validExchs:
    kfPrices = getPrices('kf', kf, ccy)
    objs.append(kfPrices)
  Parallel(n_jobs=len(objs), backend='threading')(delayed(obj.run)() for obj in objs)
  #####
  d = dict()
  oneDayShortSpotEdge = getOneDayShortSpotEdge(fundingDict)
  if 'ftx' in validExchs:
    ftxAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['FTX_' + ccy + '_ADJ_BPS']) / 10000
    d['ftxBasis'] = ftxPrices.fut / ftxPrices.spot - 1
    d['ftxSmartBasis'] = ftxGetOneDayShortFutEdge(ftx,fundingDict, d['ftxBasis']) - oneDayShortSpotEdge + ftxAdj
  if 'bb' in validExchs:
    bbAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['BB_' + ccy + '_ADJ_BPS']) / 10000
    d['bbBasis'] = bbPrices.fut / ftxPrices.spot - 1
    d['bbSmartBasis'] = bbGetOneDayShortFutEdge(bb,fundingDict, d['bbBasis']) - oneDayShortSpotEdge + bbAdj
  if 'bbt' in validExchs:
    bbtAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['BBT_' + ccy + '_ADJ_BPS']) / 10000
    d['bbtBasis'] = bbtPrices.fut * ftxPrices.spotUSDT / ftxPrices.spot - 1
    d['bbtSmartBasis'] = bbtGetOneDayShortFutEdge(bb, fundingDict, d['bbtBasis']) - oneDayShortSpotEdge + bbtAdj
  if 'bn' in validExchs:
    bnAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['BN_' + ccy + '_ADJ_BPS']) / 10000
    d['bnBasis'] = bnPrices.fut / ftxPrices.spot - 1
    d['bnSmartBasis'] = bnGetOneDayShortFutEdge(bn, fundingDict, d['bnBasis']) - oneDayShortSpotEdge + bnAdj
  if 'bnt' in validExchs:
    bntAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['BNT_' + ccy + '_ADJ_BPS']) / 10000
    d['bntBasis'] = bntPrices.fut * ftxPrices.spotUSDT / ftxPrices.spot - 1
    d['bntSmartBasis'] = bntGetOneDayShortFutEdge(bn, fundingDict, d['bntBasis']) - oneDayShortSpotEdge + bntAdj
  if 'kf' in validExchs:
    kfAdj = 0 if isSkipAdj else (CT_CONFIGS_DICT['SPOT_' + ccy + '_ADJ_BPS'] - CT_CONFIGS_DICT['KF_' + ccy + '_ADJ_BPS']) / 10000
    d['kfBasis']= kfPrices.fut / ftxPrices.spot - 1
    d['kfSmartBasis'] = kfGetOneDayShortFutEdge(kfPrices.kfTickers,fundingDict, d['kfBasis']) - oneDayShortSpotEdge + kfAdj
  return d

#############################################################################################

###############
# CryptoAlerter
###############
def caRun(ccy, color):
  def process(exch, fundingDict, smartBasisDict, isEst2, color):
    smartBasisBps = smartBasisDict[exch + 'SmartBasis'] * 10000
    basisBps = smartBasisDict[exch + 'Basis'] * 10000
    if isEst2:
      est1=fundingDict[exch+'EstFunding1']
      est2=fundingDict[exch+'EstFunding2']
      n=23
    else:
      est1=fundingDict[exch+'EstFunding']
      n=20
    z = exch.upper() + ':' + str(round(smartBasisBps)) + '/' + str(round(basisBps)) + 'bps(' + str(round(est1 * 100))
    if isEst2: z = z + '/' + str(round(est2 * 100))
    z += ')'
    print(termcolor.colored(z.ljust(n), color), end='')
  #####
  printHeader(ccy+'Alerter')
  col1N = 20
  print('Column 1:'.ljust(col1N)+'USD marginal rate / USDT marginal rate')
  print('Columns 2+:'.ljust(col1N)+'Smart basis / raw basis (est. funding rate)')
  print()
  #####
  validExchs=getValidExchs(ccy)
  ftx=ftxCCXTInit() if 'ftx' in validExchs else None
  bb=bbCCXTInit() if ('bb' in validExchs or 'bbt' in validExchs) else None
  bn=bnCCXTInit() if ('bn' in validExchs or 'bnt' in validExchs) else None
  kf=kfApophisInit() if 'kf' in validExchs else None
  #####
  while True:
    fundingDict = getFundingDict(ftx,bb,bn,kf,ccy,isRateLimit=True)
    smartBasisDict = getSmartBasisDict(ftx,bb,bn,kf,ccy, fundingDict, isSkipAdj=True)
    print(datetime.datetime.today().strftime('%H:%M:%S').ljust(10),end='')
    print(termcolor.colored((str(round(fundingDict['ftxEstMarginalUSD'] * 100))+'/'+str(round(fundingDict['ftxEstMarginalUSDT'] * 100))).ljust(col1N-10),'red'),end='')
    for exch in validExchs:
      process(exch, fundingDict, smartBasisDict, exch in ['bb', 'bbt', 'kf'], color)
    print()

#############################################################################################

##############
# CryptoTrader
##############
def ctInit(ccy=None, notional=None):
  ftx = ftxCCXTInit()
  bb = bbCCXTInit()
  bn = bnCCXTInit()
  kf = kfApophisInit()
  spotBTC=ftxGetMid(ftx,'BTC/USD')
  spotETH=ftxGetMid(ftx,'ETH/USD')
  spotXRP=ftxGetMid(ftx,'XRP/USD')
  trade_btc = np.min([np.min([CT_CONFIGS_DICT['TRADE_BTC_NOTIONAL'], CT_CONFIGS_DICT['MAX_NOTIONAL']]) / spotBTC, CT_CONFIGS_DICT['MAX_BTC']])
  trade_eth = np.min([np.min([CT_CONFIGS_DICT['TRADE_ETH_NOTIONAL'], CT_CONFIGS_DICT['MAX_NOTIONAL']]) / spotETH, CT_CONFIGS_DICT['MAX_ETH']])
  trade_xrp = np.min([np.min([CT_CONFIGS_DICT['TRADE_XRP_NOTIONAL'], CT_CONFIGS_DICT['MAX_NOTIONAL']]) / spotXRP, CT_CONFIGS_DICT['MAX_XRP']])
  trade_btc_notional = trade_btc * spotBTC
  trade_eth_notional = trade_eth * spotETH
  trade_xrp_notional = trade_xrp * spotXRP
  qty_dict = dict()
  qty_dict['BTC'] = trade_btc
  qty_dict['ETH'] = trade_eth
  qty_dict['XRP'] = trade_xrp
  notional_dict = dict()
  notional_dict['BTC'] = trade_btc_notional
  notional_dict['ETH'] = trade_eth_notional
  notional_dict['XRP'] = trade_xrp_notional
  if not (ccy is None or notional is None):
    spot=ftxGetMid(ftx, ccy + '/USD')
    qty_dict[ccy]= np.min([notional, CT_CONFIGS_DICT['MAX_NOTIONAL']]) / spot
    notional_dict[ccy]= qty_dict[ccy] * spot
  printHeader('CryptoTrader')
  print('Qtys:     ', qty_dict)
  print('Notionals:', notional_dict)
  print()
  return ftx,bb,bn,kf,qty_dict,notional_dict

def ctGetSuffix(tgtBps, realizedSlippageBps):
  z= termcolor.colored('Target: ' + str(round(tgtBps)) + 'bps', 'red')
  if len(realizedSlippageBps) > 0:
    z += ''.ljust(15) + termcolor.colored('Avg realized slippage:  ' + str(round(np.mean(realizedSlippageBps))) + 'bps', 'red')
  return z

def ctTooFewCandidates(i, tgtBps, realizedSlippageBps, color):
  print(('Program ' + str(i + 1) + ':').ljust(23) + termcolor.colored('************ Too few candidates ************'.ljust(65), color) + ctGetSuffix(tgtBps, realizedSlippageBps))
  chosenLong = ''
  return chosenLong

def ctStreakEnded(i, tgtBps, realizedSlippageBps, color):
  print(('Program ' + str(i + 1) + ':').ljust(23) + termcolor.colored('*************** Streak ended ***************'.ljust(65), color) + ctGetSuffix(tgtBps, realizedSlippageBps))
  prevSmartBasis = []
  chosenLong = ''
  chosenShort = ''
  return prevSmartBasis, chosenLong, chosenShort

def ctGetMaxChases(completedLegs):
  if completedLegs == 0:
    return 2
  else:
    return 888

def ctProcessFill(fill, completedLegs, isCancelled):
  if fill==0:
    if completedLegs==0:
      isCancelled=True
    else:
      print('Abnormal termination!')
      print('Leg '+str(completedLegs+1)+ ' cancelled when it should not have been')
      sys.exit(1)
  else:
    completedLegs+=1
  return completedLegs, isCancelled

def ctPrintTradeStats(longFill, shortFill, obsBasisBps, realizedSlippageBps):
  s= -((shortFill/longFill-1)*10000 - obsBasisBps)
  print(getCurrentTime() +   ': '+ termcolor.colored('Realized slippage:      '+str(round(s))+'bps','red'))
  realizedSlippageBps.append(s)
  return realizedSlippageBps

def ctRun(ccy, tgtBps, color, notional=None):
  if notional is None:
    ftx, bb, bn, kf, qty_dict, notional_dict = ctInit()
  else:
    ftx, bb, bn, kf, qty_dict, notional_dict = ctInit(ccy, notional)
  if not ccy in qty_dict:
    print('Invalid ccy!')
    sys.exit(1)
  trade_qty = qty_dict[ccy]
  trade_notional = notional_dict[ccy]
  realizedSlippageBps = []
  for i in range(CT_CONFIGS_DICT['NPROGRAMS']):
    prevSmartBasis = []
    chosenLong = ''
    chosenShort = ''
    while True:
      fundingDict=getFundingDict(ftx, bb, bn, kf, ccy, isRateLimit=True)
      smartBasisDict = getSmartBasisDict(ftx, bb, bn, kf, ccy, fundingDict)
      smartBasisDict['spotSmartBasis'] = 0
      smartBasisDict['spotBasis'] = 0

      # Remove disabled instruments
      for exch in SHARED_CCY_DICT[ccy]['futExch'] + ['spot']:
        if CT_CONFIGS_DICT[exch.upper() + '_' + ccy + '_OK'] == 0:
          del smartBasisDict[exch + 'SmartBasis']
          del smartBasisDict[exch+'Basis']

      # Remove spots when high spot rate
      if CT_CONFIGS_DICT['IS_HIGH_USD_RATE_PAUSE'] and fundingDict['ftxEstMarginalUSD'] >= 1:
        for key in filterDict(smartBasisDict, 'spot'):
          del smartBasisDict[key]

      # Filter dictionary
      d = filterDict(smartBasisDict, 'SmartBasis')

      # Check for too few candidates
      if len(d.keys())<2:
        chosenLong = ctTooFewCandidates(i, tgtBps, realizedSlippageBps, color)
        continue  # to next iteration in While True loop

      # If pair not lock-in yet
      if chosenLong=='':

        # Pick pair to trade
        while True:
          keyMax=max(d.items(), key=operator.itemgetter(1))[0]
          keyMin=min(d.items(), key=operator.itemgetter(1))[0]
          smartBasisBps=(d[keyMax]-d[keyMin])*10000
          chosenLong = keyMin[:len(keyMin) - 10]
          chosenShort = keyMax[:len(keyMax) - 10]
          if not CT_CONFIGS_DICT['IS_NO_FUT_BUYS_WHEN_LONG']:
            break
          if chosenLong=='ftx':
            pos=ftxGetFutPos(ftx,ccy)
          elif chosenLong=='bb':
            pos=bbGetFutPos(bb,ccy)
          elif chosenLong=='bbt':
            pos=bbtGetFutPos(bb,ccy)
          elif chosenLong=='bn':
            pos=bnGetFutPos(bn,ccy)
          elif chosenLong=='bnt':
            pos=bntGetFutPos(bn, ccy)
          elif chosenLong=='kf':
            pos=kfGetFutPos(kf,ccy)
          else:
            break
          if pos>=0:
            if len(d.keys())<=2:
              chosenLong = ctTooFewCandidates(i, tgtBps, realizedSlippageBps, color)
              time.sleep(1)
              continue # to next iteration in innermost While True loop
            else:
              del d[chosenLong+'SmartBasis']
          else:
            break

        # If target not reached yet ....
        if smartBasisBps<tgtBps:
          z = ('Program ' + str(i + 1) + ':').ljust(23)
          z += termcolor.colored((ccy+' (buy ' + chosenLong + '/sell '+chosenShort+') smart basis: '+str(round(smartBasisBps))+'bps').ljust(65),color)
          z += ctGetSuffix(tgtBps, realizedSlippageBps)
          print(z)
          chosenLong = ''
          continue # to next iteration in While True loop
        else:
          status=0

      # Maintenance
      try:
        smartBasisBps = (smartBasisDict[chosenShort+'SmartBasis'] - smartBasisDict[chosenLong+'SmartBasis'])* 10000
      except:
        prevSmartBasis, chosenLong, chosenShort = ctStreakEnded(i, tgtBps, realizedSlippageBps, color)
        continue # to next iteration in While True Loop
      basisBps      = (smartBasisDict[chosenShort+'Basis']      - smartBasisDict[chosenLong+'Basis'])*10000
      prevSmartBasis.append(smartBasisBps)
      prevSmartBasis= prevSmartBasis[-CT_CONFIGS_DICT['STREAK']:]
      isStable= (np.max(prevSmartBasis)-np.min(prevSmartBasis)) <= CT_CONFIGS_DICT['STREAK_RANGE_BPS']

      # If target reached ....
      if smartBasisBps>=tgtBps:
        status+=1
      else:
        prevSmartBasis, chosenLong, chosenShort = ctStreakEnded(i, tgtBps, realizedSlippageBps, color)
        continue # to next iteration in While True Loop

      # Chosen long/short legs
      z = ('Program ' + str(i + 1) + ':').ljust(20) + termcolor.colored(str(status).rjust(2), 'red') + ' '
      z += termcolor.colored((ccy + ' (buy ' + chosenLong + '/sell '+chosenShort+') smart/raw basis: ' + str(round(smartBasisBps)) + '/' + str(round(basisBps)) + 'bps').ljust(65), color)
      print(z + ctGetSuffix(tgtBps, realizedSlippageBps))

      if abs(status) >= CT_CONFIGS_DICT['STREAK'] and isStable:
        print()
        speak('Go')
        completedLegs = 0
        isCancelled=False
        if 'bb' == chosenLong and not isCancelled:
          longFill = bbRelOrder('BUY', bb, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'bb' == chosenShort and not isCancelled:
          shortFill = bbRelOrder('SELL', bb, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if 'bbt' == chosenLong and not isCancelled:
          longFill = bbtRelOrder('BUY', bb, ccy, trade_qty,maxChases=ctGetMaxChases(completedLegs)) * ftxGetMid(ftx, 'USDT/USD')
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'bbt' == chosenShort and not isCancelled:
          shortFill = bbtRelOrder('SELL', bb, ccy, trade_qty,maxChases=ctGetMaxChases(completedLegs)) * ftxGetMid(ftx, 'USDT/USD')
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if 'kf' == chosenLong and not isCancelled:
          longFill = kfRelOrder('BUY', kf, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'kf' == chosenShort and not isCancelled:
          shortFill = kfRelOrder('SELL', kf, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'spot' == chosenLong and not isCancelled:
          longFill = ftxRelOrder('BUY', ftx, ccy + '/USD', trade_qty, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'spot' == chosenShort and not isCancelled:
          shortFill = ftxRelOrder('SELL', ftx, ccy + '/USD', trade_qty, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'ftx' == chosenLong and not isCancelled:
          longFill = ftxRelOrder('BUY', ftx, ccy + '-PERP', trade_qty, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'ftx' == chosenShort and not isCancelled:
          shortFill = ftxRelOrder('SELL', ftx, ccy + '-PERP', trade_qty, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'bn' == chosenLong and not isCancelled:
          longFill = bnRelOrder('BUY', bn, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'bn' == chosenShort and not isCancelled:
          shortFill = bnRelOrder('SELL', bn, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'bnt' == chosenLong and not isCancelled:
          longFill = bntRelOrder('BUY', bn, ccy, trade_qty, maxChases=ctGetMaxChases(completedLegs)) * ftxGetMid(ftx, 'USDT/USD')
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'bnt' == chosenShort and not isCancelled:
          shortFill = bntRelOrder('SELL', bn, ccy, trade_qty, maxChases=ctGetMaxChases(completedLegs)) * ftxGetMid(ftx, 'USDT/USD')
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)

        if isCancelled:
          status=(min(abs(status),CT_CONFIGS_DICT['STREAK'])-1)*np.sign(status)
          print()
          speak('Cancelled')
          continue # to next iteration in While True loop
        else:
          realizedSlippageBps = ctPrintTradeStats(longFill, shortFill, basisBps, realizedSlippageBps)
          print(getCurrentTime() + ': Done')
          print()
          speak('Done')
          break # Go to next program
  speak('All done')

#############################################################################################

#####
# Etc
#####
# Add unique item to list
def appendUnique(myList,item):
  if item not in myList:
    myList.append(item)

# Cache items in memory
def cache(mode,key,value=None):
  if not hasattr(cache, 'cacheDict'):
    cache.cacheDict=dict()
  if mode=='w':
    cache.cacheDict[key]=value
  elif mode=='r':
    try:
      return cache.cacheDict[key]
    except:
      return None

# Delay in CryptoTools based on currency choices
def ccyDelay(ccy, base=0):
  if not ccy in ['BTC','ETH']:
    base+=1
  time.sleep(base)

# Cast column of dataframe to float
def dfSetFloat(df,colName):
  df[colName] = df[colName].astype(float)

# Get EMA now
def getEMANow(valueNow,emaPrev,k):
  return valueNow*k + emaPrev*(1-k)

# Filter dictionary by keyword
def filterDict(d, keyword):
  d2 = dict()
  for (key, value) in d.items():
    if keyword in key:
      d2[key] = value
  return d2

# Get current time
def getCurrentTime():
  return datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')

# Get values over next 1440 minutes (one day) with exponential decay features
def getOneDayDecayedValues(current,terminal,halfLifeHours):
  halfLifeMinutes=halfLifeHours*60
  values = [1.0 * (0.5 ** (1 / halfLifeMinutes)) ** i for i in range(1,1441)]  # 1min, 2min .... 1440mins
  values = [i * (current - terminal) + terminal for i in values]
  return values

# Get mean over next specified minutes with exponential decay features
def getOneDayDecayedMean(current,terminal,halfLifeHours,nMinutes=1440):
  return np.mean(getOneDayDecayedValues(current,terminal,halfLifeHours)[:nMinutes])

# Get percent of funding period that has elapsed
def getPctElapsed(hoursInterval):
  utcNow = datetime.datetime.utcnow()
  return (utcNow.hour * 3600 + utcNow.minute * 60 + utcNow.second) % (hoursInterval * 3600) / (hoursInterval * 3600)

# Get valid currencies for a futures exchange
def getValidCcys(futExch):
  myL = []
  for ccy in SHARED_CCY_DICT.keys():
    if futExch in SHARED_CCY_DICT[ccy]['futExch']:
      myL.append(ccy)
  return myL

# Get valid exchanges for a currency
def getValidExchs(ccy):
  myL=[]
  for futExch in SHARED_CCY_DICT[ccy]['futExch']:
    if SHARED_EXCH_DICT[futExch]==1:
      myL.append(futExch)
  return myL

# Print dictionary
def printDict(d, indent=0, isSort=True):
  keys=d.keys()
  if isSort:
    keys=sorted(keys)
  for key in keys:
    value=d[key]
    print('\t' * indent + str(key))
    if isinstance(value, dict):
      printDict(value, indent + 1, isSort=isSort)
    else:
      print('\t' * (indent + 1) + str(value))

# Print header
def printHeader(header=''):
  print()
  print('-' * 100)
  print()
  if len(header) > 0:
    print('['+header+']')
    print()

# Sleep until time chosen
def sleepUntil(h, m, s):
  t = datetime.datetime.today()
  future = datetime.datetime(t.year, t.month, t.day, h, m, s)
  if future < t:
    future += datetime.timedelta(days=1)
  fmt = '%Y-%m-%d %H:%M:%S'
  print('Current time is', t.strftime(fmt))
  print('Sleeping until ', future.strftime(fmt), '....')
  print('')
  time.sleep((future - t).seconds+1)

# Speak text
def speak(text):
  try:
    import win32com.client as wincl
    speaker = wincl.Dispatch("SAPI.SpVoice")
    speaker.Voice = speaker.getvoices()[1]
    speaker.Speak(text)
  except:
    print('[Speaking: "'+text+'"]')
    print()