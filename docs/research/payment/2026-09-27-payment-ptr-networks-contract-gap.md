# Payment PTR network inquiry: verified partial contract and acquisition gap

Observed: 2026-09-27
Scope: payment
Status: snapshot

This is evidence for [#62](https://github.com/proletariat64/dogopencli/issues/62),
not an implementation-ready contract. Inquiry-only signed-in Chrome research
observed native Search and pagination; no mutations, bank values, record IDs or
authentication material were persisted.

The native iframe is
`https://igfc.alipay.com/receivedPayment/receivedPaymentPtr/fundOutNetworkBaseline`.
The verified query is `GET https://iglobalfundcontrol.alipay.com/api/fundOutNetwork/query.json`.
The default request sends `pageSize=10`; native UI page two sends `pageNo=1`.
The response confirms zero-based page numbering and total 2,188 during research.
No business or direction filter was present in the observed default request.

## Total and identity warning

The response groups child network records in parent account records under
`fundOutNetworkBaselineDetailVOS`. A successful `pageSize=100` inquiry returned
**89 parent rows and 100 child entries**, with 100 distinct child IDs, while
`totalCount=2188`. Thus this total measures child network entries, not the outer
list length. Generic `len(resultDataList) == totalCount` completeness validation
would be wrong here. Flattening or stable parent-child identity remains a domain
decision requiring full-scope proof; aliases/bank names cannot become IDs.

Parent fields include `bankAccount`, `currencyCode`, `creditCurrency` and
`inOrOut`. A proposed account/currency composite was not validated across the
complete dataset. Native table headers include 流入流出, so the existence of
an outflow menu and the endpoint name cannot establish an exclusively outflow
result set. The exact direction enum and fixed outflow predicate still require
verification. No guessed `OUT`/`OUTFLOW` filter is authorized by this evidence.

## Acquisition attempts and blocker

The small native pages and page-size 100 query succeeded. Full-range attempts
with page size 1,000 and 5,000 failed after prolonged waiting with browser fetch
errors. A bounded page-size 2,500 retry aborted after 90 seconds without a JSON
response. These failures do not prove permission denial, a backend maximum page
size, an empty range or stable completeness. No second successful full read exists.
The cause of large-query failure is unknown.

After the operator reported that network connectivity had recovered, a new
authenticated session again completed native size-10 requests and page-one
navigation successfully (total 2,188). A fresh bounded page-zero/size-2,500
request still timed out after 90 seconds without JSON. No confirmation read
was attempted after that failure. Earlier failures may have involved the known
network outage; the recovered-session timeout still leaves full acquisition,
full identity uniqueness and direction enumeration unproved. It does not prove
a backend limit or authorize increasing retry duration indefinitely.

Consequently, no fixed single-page strategy is verified. A paginated strategy
would need child-total accounting, stable identity, cross-page overlap checks,
last/overrun proof and repeated content comparison. Do not inherit the successful
5,000-row **case** acquisition strategy for networks, or deduplicate partial
pages and label the result complete. Keep networks deferred and unregistered
until a bounded complete strategy is demonstrated.

## Native controls observed

| Native label | Input ID |
| --- | --- |
| 业务线 | `mainBusinessLine` |
| 流出银存 | `bankAccount` |
| 清算网络 | `clearingNetworkTypeCode` |
| 收款地区 | `creditRegion` |
| 流出币种 | `debtorCurrencyCode` |
| 流出渠道 | `financialInst` |
| PTR验证结果 | `verifyResult` |
| PTR巡检状态 | `inspectionStatus` |
| 是否绑定巡检规则 | `isExistInspectionRule` |
| 账户类型 | `accountType` |
| 是否纳入PTR验证范围 | `isVerifyRange` |
| 是否有可用收款卡 | `hasVaildCreditorAccount` |
| 是否收付产品标准账户 | `whetherStandard` |
| 巡检规则名称 | `inspectionRuleName` |

Input IDs are DOM evidence, not backend filter contracts. Ticket candidates for
entity, channel, account alias, payment/receipt currency, region, clearing
network, OBO/FVT, update time, verification result, patrol state, PTR inclusion
and usable beneficiary account remain **deferred** until their returned-field
and parent/child matching semantics are frozen. Do not collapse these distinct
capability, eligibility, verification and patrol concepts into one health value.

A native `账户详情` action was visible. It is account detail, not proof of a
network-baseline detail with matching network identity. No network `get` is
verified; defer it. Backend statistical units/windows, version semantics,
complete empty scope and business-rejection envelopes remain unverified.

## Sanitized partial schema

In the successful 100-child sample, `(bankAccount, currencyCode, creditCurrency)`
had 89 distinct tuples for 89 parents; `bankAccount` alone had only 86. This is
sample uniqueness, not a frozen composite identity.

Parent string fields: `accountStatus`, `financialInst`, `mainBusinessLine`,
`inOrOut`, `isVerifyRange`, `bankAccount`, `creditCurrency`, `accountType`,
`creditRegion`, `hasVaildCreditorAccount`, `whetherStandard`, `legalEntity`,
`currencyCode`. `crossCurrency` is boolean; `fundOutNetworkBaselineDetailVOS`
is an array.

Child string fields: `id`, `integrationMode`, `isPauseInspection`,
`clearingSystemStatus`, `isExistInspectionRule`, `transferTypeList`,
`noPassTerm`, `runTimeSupportObo`, `inspectionNoPassTerm`, `communicationMode`,
`runTimeSupportFvt`, `clearingNetworkTypeCode`, `inspectionStatus`,
`channelAbilityList`, `clearingSystemType`, `verifyResult`, `inspectionResult`.
Despite their names, `transferTypeList` and `channelAbilityList` were strings,
not arrays. `sameChannelFundOutNetworkBaselinePerformance` and
`fundOutNetworkBaselinePerformance` were objects; their complete nested contract
is not frozen. `supportObo`, `regulationRequire`, `supportOboIgnore`, `isFvt`
were booleans. `lastVerifyResultUpdateTime`, `runTimeAverageEfficiency`,
`costLevel`, `efficiencyLevel`, `lastInspectionResultUpdateTime` were integers;
units and statistical windows remain unverified.
