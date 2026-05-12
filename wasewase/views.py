from django.http import HttpResponse

def index(request):
    # こっから下がHTML
    return HttpResponse("""
        <div style="text-align: center; margin-top: 100px; font-family: sans-serif;">
            <h1 style="color: #4E2A84; font-size: 3rem;">わせわせ</h1>
            <p style="font-size: 1.2rem;">早大生のための、教材売買プラットフォーム（仮）</p>
            
            <button style="padding: 10px 20px; background-color: #4E2A84; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 1rem;">
                新規登録（準備中）
            </button>

            <div style="margin-top: 50px; color: #666;">
                <p>現在、主にバックエンド：池田知喜</p>
                <p>主にフロントエンド：よっぴー（ガチで無能）</p>
            </div>
        </div>
    """)