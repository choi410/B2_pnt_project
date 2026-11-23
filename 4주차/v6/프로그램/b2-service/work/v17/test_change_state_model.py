"""Explicit local-model regression: run as a module; never writes live records."""
import json,os,re,tempfile


# These expected conclusions are independent of the model output.
CASES=[
 ('request_then_agreement', '''회의명: 기본 사양 협의
논의: 고객은 압연 속도 120 m/min을 요청했다. 설계자는 검토 가능하다고 설명했다.
점검 커버는 여닫이 방식을 적용한다. 통로 치수는 별도 확인한다.
결정사항: 압연 속도는 120 m/min, 점검 커버는 여닫이 방식으로 합의했다. 이 두 항목을 기본 설계의 기준으로 사용한다.
장비 납품일은 2026-12-18로 합의했다. 설치일은 정하지 않았다.''',
  [('120 m/min','확정','L004'),('여닫이','확정','L004'),('2026-12-18','확정','L005')]),
 ('independent_final_states', '''회의명: 신규 건조 설비 협의
고객은 건조 온도 상한 165 ℃를 요청했다.
고객과 PM은 건조 온도 상한을 165 ℃로 최종 합의했다.
고객이 권취 장력 32 N을 요청했으나 이 항목은 합의하지 않았다. 장력은 검토 후 결정할 예정이다.''',
  [('165','확정','L003'),('32 N','요청','L004')]),
 ('negative_decision', '''회의명: 이송 조건 검토
고객은 이송 속도 85 m/min을 요청했다.
결정사항: 이송 속도 85 m/min 적용은 합의하지 않았다. 승인된 상태가 아니며 검토 후 결정할 예정이다.''',
  [('85 m/min','요청','L003')]),
 ('four_states', '''고객과 PM은 필름 폭을 620 mm로 합의했다.
고객이 권취 장력 65 N을 요청했다. 아직 승인하지 않았다.
고객은 HMI 영어 표시를 요청했으나 번역 범위를 정하지 못해 해당 요청을 보류했다.
고객은 커버 색상 RAL7035 요청을 철회했다. 새로운 색상은 정하지 않았다.''',
  [('620 mm','확정','L001'),('65 N','요청','L002'),('영어','보류','L003'),('RAL7035','철회','L004')]),
 ('negative_withdrawal_and_future_hold', '''권취 장력 28 N 요청은 철회하지 않았다. 아직 승인하지 않아 요청 상태로 둔다.
고객이 납품일 2027-02-18을 요청했다. 해당 요청의 보류 여부는 다음 회의에서 검토할 예정이며, 이번 회의에서는 보류하거나 승인하지 않았다.''',
  [('28 N','요청','L001'),('2027-02-18','요청','L002')]),
 ('old_decision_new_request', '''지난 회의에서 이송 속도 70 m/min으로 확정했으며 기존 기준이다.
이번 회의에서 고객은 이송 속도를 70 m/min에서 90 m/min으로 바꿔 달라고 요청했다.
90 m/min 변경에는 합의하지 않았다. 검토 후 결정하며 기존 기준은 그대로다.''',
  [('90 m/min','요청','L003')]),
 ('conclusion_before_discussion', '''결정사항: 건조 온도 상한은 172 ℃로 최종 합의했다.
논의 경과: 고객이 건조 온도 상한 172 ℃를 요청하여 검토했고, 위 결정사항으로 결론을 기록했다.''',
  [('172','확정','L001')]),
]


def check(result,expected):
 items=result['items'];compact=lambda s:re.sub(r'\s+','',s)
 assert len(items)==len(expected),(len(items),len(expected))
 for value,state,final_line in expected:
  matches=[x for x in items if compact(value) in compact(x['after'])]
  assert len(matches)==1,(value,matches)
  item=matches[0]
  assert item['business_state']==state,(value,state,item)
  assert final_line in item['evidence'],('missing conclusion evidence',value,item)
  if state=='확정':assert not re.search(r'요청(?:함|했다)?[.]?$',item['after']),item


def main():
 with tempfile.TemporaryDirectory(prefix='b2-state-model-') as temp:
  os.environ.update(B2_TEAM_DATA_DIR=temp,B2_TEAM_TESTING='1',B2_DEMO_MODE='1')
  from work.v17 import changes as ch,server as w
  from server import lines
  failed=[]
  for name,source,expected in CASES:
   print('RUN '+name,flush=True)
   try:
    result,seconds=ch.extract_changes(w,{'lines':lines(source)},[])
    print(json.dumps({'case':name,'seconds':seconds,'items':result['items']},ensure_ascii=False),flush=True)
    check(result,expected)
    print('PASS '+name,flush=True)
   except Exception as error:
    failed.append(name);print('FAIL '+name+' '+str(error),flush=True)
  assert not failed,failed
  print(f'PASS: {len(CASES)} real-model cases, including negation, mixed subjects, final evidence and prior agreements.',flush=True)


if __name__=='__main__':main()
