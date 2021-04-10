################
# Crypto Library
################
from CryptoParams import *
import pandas as pd
import numpy as np
import datetime
import sys
import time
import operator
import termcolor
import ccxt
import apophis
from retrying import retry

###########
# Functions
###########
def ftxCCXTInit():
  return ccxt.ftx({'apiKey': API_KEY_FTX, 'secret': API_SECRET_FTX, 'enableRateLimit': True})

def bbCCXTInit():
  return ccxt.bybit({'apiKey': API_KEY_BB, 'secret': API_SECRET_BB, 'enableRateLimit': True})

def bnCCXTInit():
  return  ccxt.binance({'apiKey': API_KEY_BN, 'secret': API_SECRET_BN, 'enableRateLimit': True})

def dbCCXTInit():
  return  ccxt.deribit({'apiKey': API_KEY_DB, 'secret': API_SECRET_DB, 'enableRateLimit': True})

def kfInit():
  return apophis.Apophis(API_KEY_KF,API_SECRET_KF,True)

def krCCXTInit():
  return ccxt.kraken({'apiKey': API_KEY_KR, 'secret': API_SECRET_KR, 'enableRateLimit': False})

def cbCCXTInit():
  return ccxt.coinbase({'apiKey': API_KEY_CB, 'secret': API_SECRET_CB, 'enableRateLimit': True})

#############################################################################################

@retry(wait_fixed=1000)
def ftxGetWallet(ftx):
  wallet = pd.DataFrame(ftx.private_get_wallet_all_balances()['result']['main']).set_index('coin')
  dfSetFloat(wallet,wallet.columns)
  wallet['spot']=wallet['usdValue']/wallet['total']
  return wallet

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
  def ftxGetBid(ftx,ticker):
    return float(ftx.publicGetMarketsMarketName({'market_name':ticker})['result']['bid'])
  @retry(wait_fixed=1000)
  def ftxGetAsk(ftx,ticker):
    return float(ftx.publicGetMarketsMarketName({'market_name':ticker})['result']['ask'])
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
  if ticker[:3] == 'BTC':
    qty = round(trade_qty, 3)
  elif ticker[:3] == 'ETH':
    qty = round(trade_qty, 2)
  else:
    sys.exit(1)
  print(getCurrentTime()+': Sending FTX '+side+' order of '+ticker+' (qty='+str(round(qty,6))+') ....')
  if side == 'BUY':
    limitPrice = ftxGetBid(ftx, ticker)
  else:
    limitPrice = ftxGetAsk(ftx, ticker)
  orderId = ftx.private_post_orders({'market': ticker, 'side': side.lower(), 'price': limitPrice, 'type': 'limit', 'size': qty})['result']['id']
  nChases=0
  while True:
    if ftxGetRemainingSize(ftx,orderId) == 0:
      break
    if side=='BUY':
      newPrice=ftxGetBid(ftx,ticker)
    else:
      newPrice=ftxGetAsk(ftx,ticker)
    if newPrice != limitPrice:
      limitPrice=newPrice
      nChases+=1
      if nChases>maxChases and ftxGetRemainingSize(ftx,orderId)==qty:
        if side == 'BUY':
          farPrice = limitPrice * .95
        else:
          farPrice = limitPrice * 1.05
        try:
          orderId = ftx.private_post_orders_order_id_modify({'order_id': orderId, 'price': farPrice})['result']['id']
        except:
          break
        if ftxGetRemainingSize(ftx, orderId) == qty:
          ftx.private_delete_orders_order_id({'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        try:
          orderId=ftx.private_post_orders_order_id_modify({'order_id':orderId,'price':limitPrice})['result']['id']
        except:
          break
    time.sleep(1)
  fill=ftxGetFillPrice(ftx,orderId)
  print(getCurrentTime() + ': Filled at '+str(round(fill,6)))
  return fill

#####

@retry(wait_fixed=1000)
def bbGetEstFunding1(bb,ccy):
  return float(bb.v2PrivateGetFundingPrevFundingRate({'symbol': ccy+'USD'})['result']['funding_rate']) * 3 * 365

@retry(wait_fixed=1000)
def bbGetEstFunding2(bb, ccy):
  return float(bb.v2PrivateGetFundingPredictedFunding({'symbol': ccy+'USD'})['result']['predicted_funding_rate']) * 3 * 365

def bbRelOrder(side,bb,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def bbGetBid(bb,ticker):
    return float(bb.fetch_ticker(ticker)['info']['bid_price'])
  @retry(wait_fixed=1000)
  def bbGetAsk(bb,ticker):
    return float(bb.fetch_ticker(ticker)['info']['ask_price'])
  @retry(wait_fixed=1000)
  def bbGetOrder(bb,ticker,orderId):
    result=bb.v2_private_get_order({'symbol': ticker, 'orderid': orderId})['result']
    if len(result)==0:
      return 0
    else:
      return result[0]
  @retry(wait_fixed=1000)
  def bbGetFillPrice(bb, ticker, orderId):
    df = pd.DataFrame(bb.v2_private_get_execution_list({'symbol': ticker, 'order_id': orderId})['result']['trade_list'])
    df['exec_qty'] = [float(n) for n in df['exec_qty']]
    df['exec_price'] = [float(n) for n in df['exec_price']]
    return (df['exec_qty'] * df['exec_price']).sum() / df['exec_qty'].sum()
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  ticker1=ccy+'/USD'
  ticker2=ccy+'USD'
  trade_notional = round(trade_notional)
  print(getCurrentTime() + ': Sending BB ' + side + ' order of ' + ticker1 + ' (notional=$'+ str(round(trade_notional))+') ....')
  if side=='BUY':
    limitPrice = bbGetBid(bb, ticker1)
    orderId = bb.create_limit_buy_order(ticker1, trade_notional, limitPrice)['info']['order_id']
  else:
    limitPrice = bbGetAsk(bb, ticker1)
    orderId = bb.create_limit_sell_order(ticker1, trade_notional, limitPrice)['info']['order_id']
  nChases=0
  while True:
    orderStatus=bbGetOrder(bb,ticker2,orderId)
    if orderStatus==0: # If order doesn't exist, it means all executed
      break
    if side=='BUY':
      newPrice=bbGetBid(bb,ticker1)
    else:
      newPrice=bbGetAsk(bb,ticker1)
    if newPrice != limitPrice:
      limitPrice = newPrice
      nChases+=1
      orderStatus = bbGetOrder(bb, ticker2, orderId)
      if orderStatus == 0:  # If order doesn't exist, it means all executed
        break
      if nChases>maxChases and float(orderStatus['cum_exec_qty'])==0:
        if side == 'BUY':
          farPrice = round(limitPrice * .95, 2)
        else:
          farPrice = round(limitPrice * 1.05, 2)
        try:
          bb.v2_private_post_order_replace({'symbol':ticker2,'order_id':orderId, 'p_r_price': farPrice})
        except:
          break
        orderStatus = bbGetOrder(bb, ticker2, orderId)
        if float(orderStatus['cum_exec_qty']) == 0:
          bb.v2_private_post_order_cancel({'symbol': ticker2, 'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        try:
          bb.v2_private_post_order_replace({'symbol':ticker2,'order_id':orderId, 'p_r_price': limitPrice})
        except:
          break
    time.sleep(1)
  fill=bbGetFillPrice(bb, ticker2, orderId)
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#####

@retry(wait_fixed=1000)
def bnGetEstFunding(bn, ccy):
  return float(pd.DataFrame(bn.dapiPublic_get_premiumindex({'symbol': ccy+'USD_PERP'}))['lastFundingRate']) * 3 * 365

def bnRelOrder(side,bn,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def bnGetBid(bn, ticker):
    return float(bn.dapiPublicGetTickerBookTicker({'symbol':ticker})[0]['bidPrice'])
  @retry(wait_fixed=1000)
  def bnGetAsk(bn, ticker):
    return float(bn.dapiPublicGetTickerBookTicker({'symbol': ticker})[0]['askPrice'])
  @retry(wait_fixed=1000)
  def bnGetOrder(bn, ticker, orderId):
    return bn.dapiPrivate_get_order({'symbol': ticker, 'orderId': orderId})
  # Do not use @retry!
  def bnPlaceOrder(bn, ticker, side, qty, limitPrice):
    return bn.dapiPrivate_post_order({'symbol': ticker, 'side': side, 'type': 'LIMIT', 'quantity': qty, 'price': limitPrice, 'timeInForce': 'GTC'})['orderId']
  # Do not use @retry!
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
  elif ccy=='ETH':
    qty=round(trade_notional/10)
  else:
    sys.exit(1)
  if side == 'BUY':
    limitPrice = bnGetBid(bn, ticker)
  else:
    limitPrice = bnGetAsk(bn, ticker)
  orderId=bnPlaceOrder(bn, ticker, side, qty, limitPrice)
  nChases=0
  while True:
    orderStatus = bnGetOrder(bn, ticker, orderId)
    if orderStatus['status']=='FILLED':
      break
    if side=='BUY':
      newPrice=bnGetBid(bn,ticker)
    else:
      newPrice=bnGetAsk(bn,ticker)
    if newPrice != limitPrice:
      limitPrice = newPrice
      nChases+=1
      orderStatus,leavesQty=bnCancelOrder(bn,ticker,orderId)
      if nChases>maxChases and leavesQty==qty:
        print(getCurrentTime() + ': Cancelled')
        return 0
      elif leavesQty==0:
        break
      else:
        orderId=bnPlaceOrder(bn, ticker, side, leavesQty, limitPrice)
    time.sleep(1)
  fill=float(orderStatus['avgPrice'])
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#####

@retry(wait_fixed=1000)
def dbGetEstFunding(db,ccy,mins=15):
  now=datetime.datetime.now()
  start_timestamp = int(datetime.datetime.timestamp(now - pd.DateOffset(minutes=mins)))*1000
  end_timestamp = int(datetime.datetime.timestamp(now))*1000
  return float(db.public_get_get_funding_rate_value({'instrument_name': ccy+'-PERPETUAL', 'start_timestamp': start_timestamp, 'end_timestamp': end_timestamp})['result'])*(60/mins)*24*365

def dbRelOrder(side,db,ccy,trade_notional,maxChases=0):
  @retry(wait_fixed=1000)
  def dbGetBid(db, ticker):
    d = db.public_get_ticker({'instrument_name': ticker})['result']
    return float(d['best_bid_price'])
  @retry(wait_fixed=1000)
  def dbGetAsk(db, ticker):
    d = db.public_get_ticker({'instrument_name': ticker})['result']
    return float(d['best_ask_price'])
  @retry(wait_fixed=1000)
  def dbGetOrder(db,orderId):
    return db.private_get_get_order_state({'order_id': orderId})['result']
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  if ccy=='BTC':
    trade_notional=round(trade_notional,-1)
  else:
    trade_notional=round(trade_notional)
  ticker = ccy + '-PERPETUAL'
  print(getCurrentTime() + ': Sending DB ' + side + ' order of ' + ticker + ' (notional=$'+ str(round(trade_notional))+') ....')
  if side=='BUY':
    limitPrice = dbGetBid(db, ticker)
    orderId=db.private_get_buy({'instrument_name':ticker,'amount':trade_notional,'type':'limit','price':limitPrice})['result']['order']['order_id']
  else:
    limitPrice = dbGetAsk(db, ticker)
    orderId=db.private_get_sell({'instrument_name':ticker,'amount':trade_notional,'type':'limit','price':limitPrice})['result']['order']['order_id']
  nChases=0
  while True:
    if dbGetOrder(db, orderId)['order_state']=='filled':
      break
    if side=='BUY':
      newPrice=dbGetBid(db,ticker)
    else:
      newPrice=dbGetAsk(db,ticker)
    if newPrice != limitPrice:
      limitPrice = newPrice
      nChases+=1
      orderStatus = dbGetOrder(db, orderId)
      if orderStatus['order_state'] == 'filled':
        break
      if nChases>maxChases and float(orderStatus['filled_amount'])==0:
        if side == 'BUY':
          farPrice = round(limitPrice * .95, 2)
        else:
          farPrice = round(limitPrice * 1.05, 2)
        try:
          db.private_get_edit({'order_id':orderId,'amount':trade_notional,'price':farPrice})
        except:
          break
        if float(dbGetOrder(db, orderId)['filled_amount'])==0:
          db.private_get_cancel({'order_id': orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        try:
          db.private_get_edit({'order_id': orderId, 'amount': trade_notional, 'price': limitPrice})
        except:
          break
    time.sleep(1)
  for n in range(3): # Try up to 3 times
    fill=float(dbGetOrder(db, orderId)['average_price'])
    if fill!=0:
      break
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

def kfCcyToSymbol(ccy):
  if ccy=='BTC':
    return 'pi_xbtusd'
  elif ccy=='ETH':
    return 'pi_ethusd'
  else:
    sys.exit(1)

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
  # Do not use @retry
  def kfGetBid(kf, symbol):
    return kfGetTickers(kf).loc[symbol,'bid']
  # Do not use @retry
  def kfGetAsk(kf, symbol):
    return kfGetTickers(kf).loc[symbol,'ask']
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
  print(getCurrentTime() + ': Sending KF ' + side + ' order of ' + symbol + ' (notional=$' + str(round(trade_notional)) + ') ....')
  if side == 'BUY':
    limitPrice = kfGetBid(kf, symbol)
  else:
    limitPrice = kfGetAsk(kf, symbol)
  orderId=kf.query('sendorder',{'orderType':'lmt','symbol':symbol,'side':side.lower(),'size':trade_notional,'limitPrice':limitPrice})['sendStatus']['order_id']
  nChases=0
  while True:
    orderStatus=kfGetOrderStatus(kf,orderId)
    if orderStatus is None:  # If order doesn't exist, it means all executed
      break
    if side=='BUY':
      newPrice=kfGetBid(kf,symbol)
    else:
      newPrice=kfGetAsk(kf,symbol)
    if newPrice != limitPrice:
      limitPrice=newPrice
      nChases+=1
      orderStatus = kfGetOrderStatus(kf, orderId)
      if orderStatus is None:  # If order doesn't exist, it means all executed
        break
      if nChases>maxChases and float(orderStatus['filledSize'])==0:
        if side == 'BUY':
          farPrice = round(limitPrice * .98,2)
        else:
          farPrice = round(limitPrice * 1.02,2)
        try:
          kf.query('editorder',{'orderId':orderId,'limitPrice':farPrice})
        except:
          break
        orderStatus = kfGetOrderStatus(kf, orderId)
        if float(orderStatus['filledSize']) == 0:
          kf.query('cancelorder',{'order_id':orderId})
          print(getCurrentTime() + ': Cancelled')
          return 0
      else:
        try:
          kf.query('editorder', {'orderId': orderId, 'limitPrice': limitPrice})
        except:
          break
    time.sleep(1)
  fill=0
  for n in range(3): # Try up to 3 times
    try:
      fill=float(kfGetFillPrice(kf, orderId)['average_price'])
    except:
      continue
    if fill!=0:
      break
  print(getCurrentTime() + ': Filled at ' + str(round(fill, 6)))
  return fill

#############################################################################################

def krRelOrder(side,kr,pair,trade_qty,maxChases=0):
  @retry(wait_fixed=1000)
  def krGetBid(kr, pair):
    return float(kr.public_get_ticker({'pair': pair})['result'][pair]['b'][0])
  @retry(wait_fixed=1000)
  def krGetAsk(kr, pair):
    return float(kr.public_get_ticker({'pair': pair})['result'][pair]['a'][0])
  # Do not use @retry!
  def krPlaceOrder(kr, pair, side, qty, limitPrice, lev):
    return kr.private_post_addorder({'pair': pair, 'type': side.lower(), 'ordertype': 'limit', 'price': limitPrice, 'volume': qty, 'leverage': 5})['result']['txid'][0]
  # Do not use @retry!
  def krCancelOrder(kr, orderId):
    try:
      kr.private_post_cancelorder({'txid': orderId})
    except:
      pass
  @retry(wait_fixed=1000)
  def krGetOrderStatus(kr, orderId):
    return kr.private_post_queryorders({'txid': orderId})['result'][orderId]
  #####
  if pair!='XXBTZUSD':
    print('Invalid Kraken pair detected!')
    sys.exit(1)
  #####
  if side != 'BUY' and side != 'SELL':
    sys.exit(1)
  qty = round(trade_qty, 3)
  print(getCurrentTime()+': Sending KR '+side+' order of '+pair+' (qty='+str(round(qty,6))+') ....')
  if side == 'BUY':
    limitPrice = krGetBid(kr, pair)
    z='Bidding'
  else:
    limitPrice = krGetAsk(kr, pair)
    z='Offering'
  print(getCurrentTime() + ': ' + z + ' at ' + str(limitPrice) + ' (qty='+str(round(qty,6))+') ....')
  orderId=krPlaceOrder(kr, pair, side, qty, limitPrice)
  nChases=0
  while True:
    orderStatus=krGetOrderStatus(kr,orderId)
    if orderStatus['status'] == 'closed':
      break
    if side=='BUY':
      newPrice=krGetBid(kr,pair)
    else:
      newPrice=krGetAsk(kr,pair)
    if newPrice != limitPrice:
      limitPrice=newPrice
      nChases+=1
      krCancelOrder(kr, orderId)
      orderStatus = krGetOrderStatus(kr, orderId)
      leavesQty=float(orderStatus['vol'])-float(orderStatus['vol_exec'])
      if nChases>maxChases and leavesQty==qty:
        print(getCurrentTime() + ': Cancelled')
        return 0
      elif leavesQty==0:
        break
      else:
        if side == 'BUY':
          z = 'Bidding' if side=='BUY' else 'Offering'
          print(getCurrentTime() + ': '+z+' at ' + str(limitPrice) + ' (qty='+str(round(leavesQty,6))+') ....')
        orderId=krPlaceOrder(kr, pair, side, leavesQty, limitPrice)
    time.sleep(1)
  orderStatus=krGetOrderStatus(kr,orderId)
  fill=float(orderStatus['price'])
  print(getCurrentTime() + ': Filled at '+str(round(fill,6)))
  return fill

#############################################################################################

####################
# Smart basis models
####################
def getFundingDict(ftx,bb,bn,db,kf):
  def getMarginal(ftxWallet,borrowS,lendingS,ccy):
    if ftxWallet.loc[ccy, 'total'] >= 0:
      return lendingS[ccy]
    else:
      return borrowS[ccy]
  #####
  ftxWallet = ftxGetWallet(ftx)
  borrowS = ftxGetEstBorrow(ftx)
  lendingS = ftxGetEstLending(ftx)
  d=dict()
  d['ftxEstBorrowUSD'] = borrowS['USD']
  d['ftxEstLendingUSD'] = lendingS['USD']
  d['ftxEstMarginalUSD'] = getMarginal(ftxWallet,borrowS,lendingS,'USD')
  d['ftxEstMarginalUSDT'] = getMarginal(ftxWallet, borrowS, lendingS, 'USDT')
  d['ftxEstLendingBTC']=  lendingS['BTC']
  d['ftxEstLendingETH']=  lendingS['ETH']
  d['ftxEstSpot']=d['ftxEstMarginalUSD']-(d['ftxEstLendingBTC']+d['ftxEstLendingETH'])/2
  d['ftxEstFundingBTC'] = ftxGetEstFunding(ftx, 'BTC')
  d['ftxEstFundingETH'] = ftxGetEstFunding(ftx, 'ETH')
  d['bbEstFunding1BTC'] = bbGetEstFunding1(bb, 'BTC')
  d['bbEstFunding1ETH'] = bbGetEstFunding1(bb, 'ETH')
  d['bbEstFunding2BTC'] = bbGetEstFunding2(bb, 'BTC')
  d['bbEstFunding2ETH'] = bbGetEstFunding2(bb, 'ETH')
  d['bnEstFundingBTC'] = bnGetEstFunding(bn, 'BTC')
  d['bnEstFundingETH'] = bnGetEstFunding(bn, 'ETH')
  d['dbEstFundingBTC'] = dbGetEstFunding(db, 'BTC')
  d['dbEstFundingETH'] = dbGetEstFunding(db, 'ETH')
  d['kfEstFunding1BTC'] = kfGetEstFunding1(kf, 'BTC')
  d['kfEstFunding1ETH'] = kfGetEstFunding1(kf, 'ETH')
  d['kfEstFunding2BTC'] = kfGetEstFunding2(kf, 'BTC')
  d['kfEstFunding2ETH'] = kfGetEstFunding2(kf, 'ETH')
  return d

#############################################################################################

def getOneDayShortSpotEdge(fundingDict):
  return getOneDayDecayedMean(fundingDict['ftxEstSpot'], BASE_SPOT_RATE, HALF_LIFE_HOURS_SPOT) / 365

def getOneDayShortFutEdge(hoursInterval,basis,snapFundingRate,estFundingRate,pctElapsedPower=1,prevFundingRate=None,isKF=False):
  # gain on projected basis mtm after 1 day
  edge=basis-getOneDayDecayedValues(basis, BASE_BASIS, HALF_LIFE_HOURS_BASIS)[-1]

  # gain on coupon from elapsed time
  pctElapsed = getPctElapsed(hoursInterval) ** pctElapsedPower
  edge += estFundingRate / 365 / (24 / hoursInterval) * pctElapsed
  hoursAccountedFor=hoursInterval*pctElapsed

  # gain on coupon from previous reset
  if not prevFundingRate is None:
    pctCaptured=1
    if isKF: # Special mod for kf
      pctCaptured-=getPctElapsed(hoursInterval)
    edge+=prevFundingRate/365/(24/hoursInterval)*pctCaptured
    hoursAccountedFor+=hoursInterval*pctCaptured

  # gain on projected funding pickup
  nMinutes = 1440 - round(hoursAccountedFor * 60)
  edge+= getOneDayDecayedMean(snapFundingRate, BASE_FUNDING_RATE, HALF_LIFE_HOURS_FUNDING, nMinutes=nMinutes) / 365 * (nMinutes/1440)

  return edge

@retry(wait_fixed=1000)
def ftxGetOneDayShortFutEdge(ftxFutures, fundingDict, ccy, basis):
  if not hasattr(ftxGetOneDayShortFutEdge,'emaBTC'):
    ftxGetOneDayShortFutEdge.emaBTC = fundingDict['ftxEstFundingBTC']
  if not hasattr(ftxGetOneDayShortFutEdge, 'emaETH'):
    ftxGetOneDayShortFutEdge.emaETH = fundingDict['ftxEstFundingETH']
  df=ftxFutures.loc[ccy+'-PERP']
  snapFundingRate=(float(df['mark']) / float(df['index']) - 1)*365
  k=2/(60 * 15 / CT_SLEEP + 1)
  if ccy=='BTC':
    ftxGetOneDayShortFutEdge.emaBTC = snapFundingRate * k + ftxGetOneDayShortFutEdge.emaBTC * (1 - k)
    smoothedSnapFundingRate=ftxGetOneDayShortFutEdge.emaBTC
  elif ccy=='ETH':
    ftxGetOneDayShortFutEdge.emaETH = snapFundingRate * k + ftxGetOneDayShortFutEdge.emaETH * (1 - k)
    smoothedSnapFundingRate = ftxGetOneDayShortFutEdge.emaETH
  else:
    sys.exit(1)
  return getOneDayShortFutEdge(1,basis,smoothedSnapFundingRate, fundingDict['ftxEstFunding' + ccy])

@retry(wait_fixed=1000)
def bbGetOneDayShortFutEdge(bb, fundingDict, ccy, basis):
  start_time = int((datetime.datetime.timestamp(datetime.datetime.now() - pd.DateOffset(minutes=15))))
  premIndex=np.mean([float(n) for n in pd.DataFrame(bb.v2_public_get_premium_index_kline({'symbol':ccy+'USD','interval':'1','from':start_time})['result'])['close']])
  premIndexClamped  = premIndex + np.clip(0.0001 - premIndex, -0.0005, 0.0005)
  snapFundingRate=premIndexClamped*365*3
  return getOneDayShortFutEdge(8, basis, snapFundingRate, fundingDict['bbEstFunding2' + ccy], prevFundingRate=fundingDict['bbEstFunding1'+ccy])

@retry(wait_fixed=1000)
def bnGetOneDayShortFutEdge(bn, fundingDict, ccy, basis):
  df=pd.DataFrame(bn.dapiData_get_basis({'pair': ccy + 'USD', 'contractType': 'PERPETUAL', 'period': '1m'}))[-15:]
  dfSetFloat(df,['basis','indexPrice'])
  premIndex=(df['basis'] / df['indexPrice']).mean()
  premIndexClamped=premIndex+np.clip(0.0001-premIndex,-0.0005,0.0005)
  snapFundingRate=premIndexClamped*365*3
  return getOneDayShortFutEdge(8, basis,snapFundingRate, fundingDict['bnEstFunding' + ccy], pctElapsedPower=2)

@retry(wait_fixed=1000)
def dbGetOneDayShortFutEdge(fundingDict, ccy, basis):
  edge = basis - getOneDayDecayedValues(basis, BASE_BASIS, HALF_LIFE_HOURS_BASIS)[-1] # basis
  edge += getOneDayDecayedMean(fundingDict['dbEstFunding' + ccy], BASE_FUNDING_RATE, HALF_LIFE_HOURS_FUNDING) / 365 # funding
  return edge

@retry(wait_fixed=1000)
def kfGetOneDayShortFutEdge(kfTickers, fundingDict, ccy, basis):
  if not hasattr(kfGetOneDayShortFutEdge, 'emaBTC'):
    kfGetOneDayShortFutEdge.emaBTC = fundingDict['kfEstFunding2BTC']
  if not hasattr(kfGetOneDayShortFutEdge, 'emaETH'):
    kfGetOneDayShortFutEdge.emaETH = fundingDict['kfEstFunding2ETH']
  symbol = kfCcyToSymbol(ccy)
  if ccy == 'BTC':
    indexSymbol = 'in_xbtusd'
  elif ccy == 'ETH':
    indexSymbol = 'in_ethusd'
  else:
    sys.exit(1)
  mid = (kfTickers.loc[symbol, 'bid'] + kfTickers.loc[symbol, 'ask']) / 2
  premIndexClipped = np.clip(mid / kfTickers.loc[indexSymbol, 'last'] - 1, -0.008, 0.008)
  snapFundingRate = premIndexClipped * 365 * 3
  k = 2 / (60 * 15 / CT_SLEEP + 1)
  if ccy == 'BTC':
    kfGetOneDayShortFutEdge.emaBTC = snapFundingRate * k + kfGetOneDayShortFutEdge.emaBTC * (1 - k)
    smoothedSnapFundingRate = kfGetOneDayShortFutEdge.emaBTC
  elif ccy == 'ETH':
    kfGetOneDayShortFutEdge.emaETH = snapFundingRate * k + kfGetOneDayShortFutEdge.emaETH * (1 - k)
    smoothedSnapFundingRate = kfGetOneDayShortFutEdge.emaETH
  else:
    sys.exit(1)
  return getOneDayShortFutEdge(4, basis, smoothedSnapFundingRate, fundingDict['kfEstFunding2' + ccy], prevFundingRate=fundingDict['kfEstFunding1' + ccy], isKF=True)

#############################################################################################

def getSmartBasisDict(ftx, bb, bn, db, kf, fundingDict, isSkipAdj=False):
  @retry(wait_fixed=1000)
  def ftxGetMarkets(ftx):
    return pd.DataFrame(ftx.public_get_markets()['result']).set_index('name')
  #####
  @retry(wait_fixed=1000)
  def ftxGetFutures(ftx):
    return pd.DataFrame(ftx.public_get_futures()['result']).set_index('name')
  #####
  def ftxGetMid(ftxMarkets, name):
    return (float(ftxMarkets.loc[name,'bid']) + float(ftxMarkets.loc[name,'ask'])) / 2
  #####
  @retry(wait_fixed=1000)
  def bbGetTickers(bb):
    return pd.DataFrame(bb.v2PublicGetTickers()['result']).set_index('symbol')
  #####
  def bbGetMid(bbTickers, ccy):
    return (float(bbTickers.loc[ccy,'bid_price']) + float(bbTickers.loc[ccy,'ask_price'])) / 2
  #####
  @retry(wait_fixed=1000)
  def bnGetBookTicker(bn):
    return pd.DataFrame(bn.dapiPublicGetTickerBookTicker()).set_index('symbol')
  #####
  def bnGetMid(bnBookTicker, ccy):
    return (float(bnBookTicker.loc[ccy+'USD_PERP','bidPrice']) + float(bnBookTicker.loc[ccy+'USD_PERP','askPrice'])) / 2
  #####
  @retry(wait_fixed=1000)
  def dbGetMid(db,ccy):
    d=db.public_get_ticker({'instrument_name': ccy+'-PERPETUAL'})['result']
    return (float(d['best_bid_price'])+float(d['best_ask_price']))/2
  #####
  oneDayShortSpotEdge = getOneDayShortSpotEdge(fundingDict)
  ftxMarkets = ftxGetMarkets(ftx)
  ftxFutures = ftxGetFutures(ftx)
  spotBTC = ftxGetMid(ftxMarkets, 'BTC/USD')
  spotETH = ftxGetMid(ftxMarkets, 'ETH/USD')
  if isSkipAdj:
    ftxBTCAdj=0
    ftxETHAdj=0
    bnBTCAdj=0
    bnETHAdj=0
    bbBTCAdj=0
    bbETHAdj=0
    dbBTCAdj=0
    dbETHAdj=0
    kfBTCAdj=0
    kfETHAdj=0
  else:
    ftxBTCAdj = (CT_CONFIGS_DICT['SPOT_BTC_ADJ_BPS'] - CT_CONFIGS_DICT['FTX_BTC_ADJ_BPS']) / 10000
    ftxETHAdj = (CT_CONFIGS_DICT['SPOT_ETH_ADJ_BPS'] - CT_CONFIGS_DICT['FTX_ETH_ADJ_BPS']) / 10000
    bbBTCAdj = (CT_CONFIGS_DICT['SPOT_BTC_ADJ_BPS'] - CT_CONFIGS_DICT['BB_BTC_ADJ_BPS']) / 10000
    bbETHAdj = (CT_CONFIGS_DICT['SPOT_ETH_ADJ_BPS'] - CT_CONFIGS_DICT['BB_ETH_ADJ_BPS']) / 10000
    bnBTCAdj = (CT_CONFIGS_DICT['SPOT_BTC_ADJ_BPS'] - CT_CONFIGS_DICT['BN_BTC_ADJ_BPS']) / 10000
    bnETHAdj = (CT_CONFIGS_DICT['SPOT_ETH_ADJ_BPS'] - CT_CONFIGS_DICT['BN_ETH_ADJ_BPS']) / 10000
    dbBTCAdj = (CT_CONFIGS_DICT['SPOT_BTC_ADJ_BPS'] - CT_CONFIGS_DICT['DB_BTC_ADJ_BPS']) / 10000
    dbETHAdj = (CT_CONFIGS_DICT['SPOT_ETH_ADJ_BPS'] - CT_CONFIGS_DICT['DB_ETH_ADJ_BPS']) / 10000
    kfBTCAdj = (CT_CONFIGS_DICT['SPOT_BTC_ADJ_BPS'] - CT_CONFIGS_DICT['KF_BTC_ADJ_BPS']) / 10000
    kfETHAdj = (CT_CONFIGS_DICT['SPOT_ETH_ADJ_BPS'] - CT_CONFIGS_DICT['KF_ETH_ADJ_BPS']) / 10000            
  #####
  d = dict()
  d['ftxBTCBasis'] = ftxGetMid(ftxMarkets, 'BTC-PERP') / spotBTC - 1
  d['ftxETHBasis'] = ftxGetMid(ftxMarkets, 'ETH-PERP') / spotETH - 1
  d['ftxBTCSmartBasis'] = ftxGetOneDayShortFutEdge(ftxFutures, fundingDict, 'BTC', d['ftxBTCBasis']) - oneDayShortSpotEdge + ftxBTCAdj
  d['ftxETHSmartBasis'] = ftxGetOneDayShortFutEdge(ftxFutures, fundingDict, 'ETH', d['ftxETHBasis']) - oneDayShortSpotEdge + ftxETHAdj
  #####
  bbTickers = bbGetTickers(bb)
  d['bbBTCBasis'] = bbGetMid(bbTickers, 'BTCUSD') / spotBTC - 1
  d['bbETHBasis'] = bbGetMid(bbTickers, 'ETHUSD') / spotETH - 1
  d['bbBTCSmartBasis'] = bbGetOneDayShortFutEdge(bb,fundingDict, 'BTC',d['bbBTCBasis']) - oneDayShortSpotEdge + bbBTCAdj
  d['bbETHSmartBasis'] = bbGetOneDayShortFutEdge(bb,fundingDict, 'ETH',d['bbETHBasis']) - oneDayShortSpotEdge + bbETHAdj
  #####
  bnBookTicker = bnGetBookTicker(bn)
  d['bnBTCBasis'] = bnGetMid(bnBookTicker, 'BTC') / spotBTC - 1
  d['bnETHBasis'] = bnGetMid(bnBookTicker, 'ETH') / spotETH - 1
  d['bnBTCSmartBasis'] = bnGetOneDayShortFutEdge(bn, fundingDict, 'BTC', d['bnBTCBasis']) - oneDayShortSpotEdge + bnBTCAdj
  d['bnETHSmartBasis'] = bnGetOneDayShortFutEdge(bn, fundingDict, 'ETH', d['bnETHBasis']) - oneDayShortSpotEdge + bnETHAdj
  ###
  d['dbBTCBasis'] = dbGetMid(db, 'BTC') / spotBTC - 1
  d['dbETHBasis'] = dbGetMid(db, 'ETH') / spotETH - 1
  d['dbBTCSmartBasis'] = dbGetOneDayShortFutEdge(fundingDict, 'BTC', d['dbBTCBasis']) - oneDayShortSpotEdge + dbBTCAdj
  d['dbETHSmartBasis'] = dbGetOneDayShortFutEdge(fundingDict, 'ETH', d['dbETHBasis']) - oneDayShortSpotEdge + dbETHAdj
  ###
  kfTickers=kfGetTickers(kf)
  d['kfBTCBasis']=(kfTickers.loc['pi_xbtusd','bid']+kfTickers.loc['pi_xbtusd','ask'])/2/spotBTC - 1
  d['kfETHBasis'] = (kfTickers.loc['pi_ethusd', 'bid'] + kfTickers.loc['pi_ethusd', 'ask']) / 2 / spotETH - 1
  d['kfBTCSmartBasis'] = kfGetOneDayShortFutEdge(kfTickers,fundingDict, 'BTC', d['kfBTCBasis']) - oneDayShortSpotEdge + kfBTCAdj
  d['kfETHSmartBasis'] = kfGetOneDayShortFutEdge(kfTickers,fundingDict, 'ETH', d['kfETHBasis']) - oneDayShortSpotEdge + kfETHAdj
  return d

#############################################################################################

##############
# CryptoTrader
##############
def ctInit():
  ftx = ftxCCXTInit()
  bb = bbCCXTInit()
  bn = bnCCXTInit()
  db = dbCCXTInit()
  kf = kfInit()
  ftxWallet=ftxGetWallet(ftx)
  spotBTC=ftxWallet.loc['BTC','spot']
  spotETH=ftxWallet.loc['ETH', 'spot']
  trade_btc = np.min([np.min([CT_TRADE_BTC_NOTIONAL, CT_MAX_NOTIONAL]) / spotBTC, CT_MAX_BTC])
  trade_eth = np.min([np.min([CT_TRADE_ETH_NOTIONAL, CT_MAX_NOTIONAL]) / spotETH, CT_MAX_ETH])
  trade_btc_notional = trade_btc * spotBTC
  trade_eth_notional = trade_eth * spotETH
  qty_dict = dict()
  qty_dict['BTC'] = trade_btc
  qty_dict['ETH'] = trade_eth
  notional_dict = dict()
  notional_dict['BTC'] = trade_btc_notional
  notional_dict['ETH'] = trade_eth_notional
  printHeader('CryptoTrader')
  print('Qtys:     ', qty_dict)
  print('Notionals:', notional_dict)
  print()
  return ftx,bb,bn,db,kf,qty_dict,notional_dict

def ctRemoveDisabledInstrument(smartBasisDict, exch, ccy):
  if CT_CONFIGS_DICT[exch + '_' + ccy + '_OK'] == 0:
    d = filterDict(smartBasisDict, 'Basis')
    d = filterDict(d, exch.lower())
    d = filterDict(d, ccy)
    for key in d:
      del smartBasisDict[key]
  return smartBasisDict

def ctGetTargetString(tgtBps):
  return termcolor.colored('Target: ' + str(round(tgtBps)) + 'bps', 'magenta')

def ctGetMaxChases(completedLegs):
  if completedLegs == 0:
    return 0
  else:
    return 888

def ctProcessFill(fill, completedLegs, isCancelled):
  if fill != 0:
    completedLegs += 1
  else:
    isCancelled = True
  return completedLegs, isCancelled

def ctPrintTradeStats(longFill, shortFill, obsBasisBps, realizedSlippageBps):
  s= -((shortFill/longFill-1)*10000 - obsBasisBps)
  print(getCurrentTime() +   ': '+ termcolor.colored('Realized slippage:      '+str(round(s))+'bps','red'))
  realizedSlippageBps.append(s)
  if len(realizedSlippageBps) > 1:
    print(getCurrentTime() + ': '+ termcolor.colored('Avg realized slippage:  '+str(round(np.mean(realizedSlippageBps))) + 'bps','red'))
  return realizedSlippageBps

def ctRun(ccy):
  ftx, bb, bn, db, kf, qty_dict, notional_dict = ctInit()
  if not ccy in ['BTC', 'ETH']:
    print('Invalid ccy!')
    sys.exit(1)
  trade_qty = qty_dict[ccy]
  trade_notional = notional_dict[ccy]
  tgtBps=CT_CONFIGS_DICT[ccy+'_TGT_BPS']
  realizedSlippageBps = []
  for i in range(CT_NPROGRAMS):
    prevSmartBasis = []
    chosenLong = ''
    chosenShort = ''
    while True:
      fundingDict=getFundingDict(ftx, bb, bn, db, kf)
      smartBasisDict = getSmartBasisDict(ftx, bb, bn, db, kf, fundingDict)
      smartBasisDict['spot' + ccy + 'SmartBasis'] = 0
      smartBasisDict['spot' + ccy + 'Basis'] = 0

      # Remove disabled instruments
      for x in ['SPOT','FTX','BB','BN','DB','KF']:
        for c in ['BTC','ETH']:
          smartBasisDict = ctRemoveDisabledInstrument(smartBasisDict, x,c)

      # Remove spots on high spot rate
      if CT_IS_HIGH_SPOT_RATE_PAUSE and fundingDict['ftxEstMarginalUSD'] >= 1:
        for key in filterDict(smartBasisDict, 'spot'):
          del smartBasisDict[key]

      if chosenLong=='':
        d=filterDict(smartBasisDict,'SmartBasis')
        d=filterDict(d,ccy)
        keyMax=max(d.items(), key=operator.itemgetter(1))[0]
        keyMin=min(d.items(), key=operator.itemgetter(1))[0]
        smartBasisBps=(d[keyMax]-d[keyMin])*10000
        chosenLong = keyMin[:len(keyMin) - 13]
        chosenShort = keyMax[:len(keyMax) - 13]
        if chosenLong==chosenShort:
          print(('Program ' + str(i + 1) + ':').ljust(23) + termcolor.colored('************ Too few candidates ************'.ljust(65), 'blue') + ctGetTargetString(tgtBps))
          chosenLong=''
          time.sleep(CT_SLEEP)
          continue  # to next iteration in While True loop
        if smartBasisBps<tgtBps:
          z = ('Program ' + str(i + 1) + ':').ljust(23)
          z += termcolor.colored((ccy+' (buy ' + chosenLong + '/sell '+chosenShort+') smart basis: '+str(round(smartBasisBps))+'bps').ljust(65),'blue')
          print(z + ctGetTargetString(tgtBps))
          chosenLong = ''
          time.sleep(CT_SLEEP)
          continue # to next iteration in While True loop
        else:
          status=0

      smartBasisBps = (smartBasisDict[chosenShort+ccy+'SmartBasis'] - smartBasisDict[chosenLong+ccy+'SmartBasis'])* 10000
      basisBps      = (smartBasisDict[chosenShort+ccy+'Basis']      - smartBasisDict[chosenLong+ccy+'Basis'])*10000
      prevSmartBasis.append(smartBasisBps)
      prevSmartBasis= prevSmartBasis[-CT_STREAK:]
      isStable= (np.max(prevSmartBasis)-np.min(prevSmartBasis)) <= CT_STREAK_BPS_RANGE

      if smartBasisBps>=tgtBps:
        status+=1
      else:
        print(('Program ' + str(i + 1) + ':').ljust(23)+ termcolor.colored('*************** Streak ended ***************'.ljust(65), 'blue') + ctGetTargetString(tgtBps))
        prevSmartBasis = []
        chosenLong = ''
        chosenShort = ''
        continue

      # Chosen long/short legs
      z = ('Program ' + str(i + 1) + ':').ljust(20) + termcolor.colored(str(status).rjust(2), 'red') + ' '
      z += termcolor.colored((ccy + ' (buy ' + chosenLong + '/sell '+chosenShort+') smart/raw basis: ' + str(round(smartBasisBps)) + '/' + str(round(basisBps)) + 'bps').ljust(65), 'blue')
      print(z + ctGetTargetString(tgtBps))

      if abs(status) >= CT_STREAK and isStable:
        print()
        speak('Go')
        completedLegs = 0
        isCancelled=False
        if 'bb' in chosenLong and not isCancelled:
          longFill = bbRelOrder('BUY', bb, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'bb' in chosenShort and not isCancelled:
          shortFill = bbRelOrder('SELL', bb, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if 'kf' in chosenLong and not isCancelled:
          longFill = kfRelOrder('BUY', kf, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'kf' in chosenShort and not isCancelled:
          shortFill = kfRelOrder('SELL', kf, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'db' in chosenLong and not isCancelled:
          longFill = dbRelOrder('BUY', db, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(longFill, completedLegs, isCancelled)
        if 'db' in chosenShort and not isCancelled:
          shortFill = dbRelOrder('SELL', db, ccy, trade_notional, maxChases=ctGetMaxChases(completedLegs))
          completedLegs, isCancelled = ctProcessFill(shortFill, completedLegs, isCancelled)
        if 'bn' in chosenLong and not isCancelled:
          longFill = bnRelOrder('BUY', bn, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'bn' in chosenShort and not isCancelled:
          shortFill = bnRelOrder('SELL', bn, ccy, trade_notional,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if 'spot' in chosenLong and not isCancelled:
          longFill = ftxRelOrder('BUY', ftx, ccy + '/USD', trade_qty,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'spot' in chosenShort and not isCancelled:
          shortFill = ftxRelOrder('SELL', ftx, ccy + '/USD', trade_qty, maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if 'ftx' in chosenLong and not isCancelled:
          longFill = ftxRelOrder('BUY', ftx, ccy + '-PERP', trade_qty,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(longFill,completedLegs,isCancelled)
        if 'ftx' in chosenShort and not isCancelled:
          shortFill = ftxRelOrder('SELL', ftx, ccy + '-PERP', trade_qty,maxChases=ctGetMaxChases(completedLegs))
          completedLegs,isCancelled=ctProcessFill(shortFill,completedLegs,isCancelled)
        if isCancelled:
          status=(min(abs(status),CT_STREAK)-2)*np.sign(status)
          print()
          speak('Cancelled')
          continue # to next iteration in While True loop
        else:
          realizedSlippageBps = ctPrintTradeStats(longFill, shortFill, basisBps, realizedSlippageBps)
          print(getCurrentTime() + ': Done')
          print()
          speak('Done')
          break # Go to next program
      time.sleep(CT_SLEEP)
  speak('All done')

#############################################################################################

#####
# Etc
#####
# Cast column of dataframe to float
def dfSetFloat(df,colName):
  df[colName] = df[colName].astype(float)

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