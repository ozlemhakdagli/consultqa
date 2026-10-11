"""Browser tests of the frontend's view helpers and selectors, imported in headless Chrome."""

import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e


def test_uses_default_library_follows_the_chosen_folder(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { usesDefaultLibrary } = await import('/js/selectors.js');
        const collections = [{ id: 'a', name: 'Belgelerim' }, { id: 'b', name: 'Ürün' }];
        return ['', 'a', 'b', 'zzz'].map((selectedCollectionId) =>
          usesDefaultLibrary({ collections, selectedCollectionId }));
        """,
    )
    assert result == [True, True, False, True]


def test_reveal_scrolls_only_when_the_top_edge_is_off_screen(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { revealIfHidden } = await import('/js/scroll.js');
        const calls = [];
        const win = { innerHeight: 800 };
        for (const top of [900, 100, -5, 400]) {
          const node = {
            getBoundingClientRect: () => ({ top }),
            scrollIntoView: (options) => calls.push([top, options]),
          };
          revealIfHidden(node, win);
        }
        return calls.filter(([, options]) => options.block === 'start').map(([top]) => top);
        """,
    )
    assert result == [900, -5]


def test_split_passage_marks_the_answer_and_its_sentence(page, base_url):
    result = run_js(
        page,
        base_url,
        r"""
        const { splitPassage } = await import('/js/highlight.js');
        const p = 'Birinci cümle. Stok modülü performans iyileştirmesi yapıldı. Üçüncü cümle.';
        return [
          splitPassage(p, 'performans iyileştirmesi yapıldı'),
          splitPassage(p, 'Stok modülü performans iyileştirmesi yapıldı.'),
          splitPassage(p, '  Birinci cümle  '),
          splitPassage('Başlık satırı\nBu bir cümle olarak devam eder', 'cümle olarak'),
          splitPassage('Sürüm 4.23 çıktı. Yeni ad soyad alanı eklendi.', 'ad soyad'),
          splitPassage('Stok modülü\nperformans iyileştirmesi yapıldı.', 'Stok modülü performans iyileştirmesi yapıldı.'),
          splitPassage(p, 'olmayan bir cevap'),
          splitPassage(p, ''),
          splitPassage(p, null),
          splitPassage('Soru nedir? Cevap budur! Sonra devam.', 'Cevap budur'),
        ];
        """,
    )
    assert result == [
        {
            "before": "Birinci cümle. ",
            "lead": "Stok modülü ",
            "answer": "performans iyileştirmesi yapıldı",
            "tail": ".",
            "after": " Üçüncü cümle.",
        },
        {
            "before": "Birinci cümle. ",
            "lead": "",
            "answer": "Stok modülü performans iyileştirmesi yapıldı.",
            "tail": "",
            "after": " Üçüncü cümle.",
        },
        {
            "before": "",
            "lead": "",
            "answer": "Birinci cümle",
            "tail": ".",
            "after": " Stok modülü performans iyileştirmesi yapıldı. Üçüncü cümle.",
        },
        {
            "before": "Başlık satırı\n",
            "lead": "Bu bir ",
            "answer": "cümle olarak",
            "tail": " devam eder",
            "after": "",
        },
        {
            "before": "Sürüm 4.23 çıktı. ",
            "lead": "Yeni ",
            "answer": "ad soyad",
            "tail": " alanı eklendi.",
            "after": "",
        },
        {
            "before": "",
            "lead": "",
            "answer": "Stok modülü\nperformans iyileştirmesi yapıldı.",
            "tail": "",
            "after": "",
        },
        None,
        None,
        None,
        {
            "before": "Soru nedir? ",
            "lead": "",
            "answer": "Cevap budur",
            "tail": "!",
            "after": " Sonra devam.",
        },
    ]


def test_theme_choice_is_validated_applied_and_remembered(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        localStorage.clear();
        const { THEMES, readTheme, chooseTheme } = await import('/js/theme.js');
        const root = document.createElement('html');
        const out = [THEMES, readTheme()];
        chooseTheme('dark', root);
        out.push(root.getAttribute('data-theme'), readTheme());
        chooseTheme('light', root);
        out.push(root.getAttribute('data-theme'));
        chooseTheme('system', root);
        out.push(root.getAttribute('data-theme'), readTheme());
        chooseTheme('neon', root);
        out.push(root.getAttribute('data-theme'), readTheme());
        localStorage.setItem('docrag.theme', 'banana');
        out.push(readTheme());
        localStorage.clear();
        return out;
        """,
    )
    assert result == [
        ["system", "light", "dark"],
        "system",
        "dark",
        "dark",
        "light",
        None,
        "system",
        None,
        "system",
        "system",
    ]
