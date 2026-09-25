"""Emerging indicators require both rising live evidence and verified local history."""
def emerging_status(summary,historical=None,linked=False):
    rows=summary.get('timeline',[])
    mid=len(rows)//2
    earlier=sum(r['high_pairs'] for r in rows[:mid])/max(mid,1)
    later=sum(r['high_pairs'] for r in rows[mid:])/max(len(rows)-mid,1)
    increasing=later>earlier+.1
    repeated=summary.get('high_interactions',0)>=3
    live_candidate=repeated and increasing
    if historical is None or not linked:
        status='Live conflict cluster' if repeated else 'Insufficient repeated evidence'
        reason='Historical coverage at this camera is unknown; an emerging geographic hotspot cannot be confirmed.'
    elif historical<=30 and live_candidate:
        status='Emerging hotspot candidate'; reason='Low recorded historical index, repeated conflicts, and increasing conflict-frame density.'
    else:
        status='Emerging criteria not met'; reason='Requires historical index ≤30, ≥3 distinct conflict episodes, and rising conflict-frame density.'
    return {'status':status,'reason':reason,'increasing':increasing,'early_rate':earlier,'late_rate':later,'repeated':repeated}
