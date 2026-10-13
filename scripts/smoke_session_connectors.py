"""Browser regression for the actual chat toolbar; APIs use isolated fixtures."""
import json
import sys
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

base = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5187'
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1280, 'height': 900})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    selections = {'first': [], 'second': []}
    state = {'fail': False}
    def api(route):
        path = urlsplit(route.request.url).path
        if '/sessions/' in path:
            session = path.rsplit('/', 1)[-1]
            if route.request.method == 'PUT':
                if state['fail']:
                    route.fulfill(status=400, json={'detail': '模拟保存失败'})
                    return
                selections[session] = route.request.post_data_json['connector_ids']
            route.fulfill(json={'connector_ids': selections[session]})
        else:
            route.fulfill(json={'enabled': True, 'items': [
                {'id': key, 'name': name, 'status': status, 'skills': [], 'tools': [], 'source': key, 'sha256': key}
                for key, name, status in [('one', 'ERP', 'connected'), ('two', 'CRM', 'connected'), ('offline', '未授权服务', 'installed')]
            ]})
    page.route('**/harbor/connectors/**', api)
    page.goto(base + '/tests/fixtures/session-connectors.html')
    menu = page.get_by_role('button', name='连接器', exact=True, include_hidden=True)
    expect(menu).to_be_visible(timeout=60000)
    menu.click()
    one = page.get_by_role('menuitemcheckbox', name='ERP')
    two = page.get_by_role('menuitemcheckbox', name='CRM')
    expect(page.get_by_role('menuitemcheckbox')).to_have_count(2)
    one.click()
    expect(one).to_be_checked()
    two.click()
    expect(two).to_be_checked()
    expect(menu).to_contain_text('2')
    page.keyboard.press('Escape')
    page.get_by_text('Switch session', exact=True).click()
    menu.click()
    expect(one).not_to_be_checked()
    expect(two).not_to_be_checked()
    page.keyboard.press('Escape')
    page.get_by_text('Switch session', exact=True).click()
    menu.click()
    expect(one).to_be_checked()
    expect(two).to_be_checked()
    one.click()
    expect(one).not_to_be_checked()
    assert selections['first'] == ['two']
    state['fail'] = True
    two.click()
    expect(page.get_by_role('alert')).to_contain_text('模拟保存失败')
    expect(two).to_be_checked()
    page.keyboard.press('Escape')
    page.get_by_text('Toggle running', exact=True).click()
    expect(menu).to_be_disabled()
    page.get_by_text('Toggle running', exact=True).click()
    page.get_by_text('Manage', exact=True).click()
    expect(page.get_by_role('heading', name='连接器', exact=True)).to_be_visible()
    body = page.locator('body').inner_text()
    assert 'workbuddy' not in body.lower()
    assert '技能安装目标' not in body and '安装到所选会话' not in body
    assert not errors, errors
    browser.close()
print('PASS: real chat multiselect, session isolation, deselect, save failure, running guard and connector page')
