exec(open('grid.py').read().split("G = {}")[0])
near5, near10 = C >= 0.95 * hi252, C >= 0.90 * hi252
ext25 = C / s50 - 1 <= 0.25
G = {}
G['00 基準'] = sel()
G['50 52週-5%＋50MA乖離25%'] = sel(extra=near5 & ext25)
G['51 52週-10%＋50MA乖離25%'] = sel(extra=near10 & ext25)
G['52 52週-5%・売買代金上位10%'] = sel(dvmin=0.90, extra=near5)
G['53 52週-5%・売買代金上位10%・RS189≥85'] = sel(dvmin=0.90, rsmin=85, extra=near5)
G['54 52週-5%・地合いなし'] = sel(reg='なし', extra=near5)
G['55 52週-5%・売買代金上位20%'] = sel(dvmin=0.80, extra=near5)
G['56 52週-3%以内'] = sel(extra=C >= 0.97 * hi252)
G['57 52週-7%以内'] = sel(extra=C >= 0.93 * hi252)
G['58 52週-15%以内'] = sel(extra=C >= 0.85 * hi252)
G['59 50MA乖離+20%以内'] = sel(extra=C / s50 - 1 <= 0.20)
G['60 50MA乖離+30%以内'] = sel(extra=C / s50 - 1 <= 0.30)
pd.to_pickle(G, 'sig_grid2.pkl')
