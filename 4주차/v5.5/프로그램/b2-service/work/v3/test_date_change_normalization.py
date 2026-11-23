from work.v17.changes import normalize_extraction

def normalize(title,after,source,topics=()):
 return normalize_extraction({'lines':[{'id':'L1','text':source}]},[{'topic_id':None,'title':title,'category':'사양','before':'','after':after,'business_state':'확정','evidence':['L1']}],topics)[0]

def test_explicit_delivery_date_repairs_category_before_and_unique_topic():
 item=normalize('납기','2026-12-23','장비 납품일을 2026-12-18에서 2026-12-23으로 변경하기로 합의했다.',[{'id':'delivery','title':'장비 납품일','category':'납기'}])
 assert (item['category'],item['title'],item['before'],item['after'],item['topic_id'])==('납기','장비 납품일','2026-12-18','2026-12-23','delivery')

def test_specification_with_a_date_is_not_turned_into_schedule():
 item=normalize('검수 조건','2026-12-23','검수일은 2026-12-23이다. 검수 조건을 다시 확인한다.')
 assert item['category']=='사양' and item['before']=='' and item['topic_id'] is None

def test_ambiguous_delivery_topics_are_not_automatically_linked():
 topics=[{'id':'machine','title':'장비 납품일','category':'납기'},{'id':'parts','title':'부품 납품일','category':'납기'}]
 item=normalize('납기','2026-12-23','장비 납품일과 부품 납품일은 2026-12-23으로 합의했다.',topics)
 assert item['category']=='납기' and item['topic_id'] is None

def test_withdrawn_request_does_not_become_agreement_on_retained_value():
 item=normalize('건조 온도 상한','120 ℃','건조로 온도 상한을 기존 120 ℃에서 140 ℃로 높이려던 변경 요청을 철회했다. 건조로 온도 상한은 기존 120 ℃를 유지한다.')
 assert (item['before'],item['after'],item['business_state'])==('120 ℃','140 ℃','철회')

def test_withdrawal_of_another_subject_does_not_change_the_event():
 item=normalize('롤러 표면 온도','120 ℃','건조로 온도 상한을 기존 120 ℃에서 140 ℃로 높이려던 변경 요청을 철회했다. 롤러 표면 온도는 120 ℃로 합의했다.')
 assert item['business_state']=='확정' and item['after']=='120 ℃'
