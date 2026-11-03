
(function () {
    var CLAVE = 'cambell-tema';
    var actual = localStorage.getItem(CLAVE) || 'oscuro';
    document.documentElement.setAttribute('data-tema', actual);

    function esClaro() {
        return document.documentElement.getAttribute('data-tema') === 'claro';
    }

    var SVG_LUNA = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    var SVG_SOL = '<svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>';

    function pintar() {
        var icono = esClaro() ? SVG_LUNA : SVG_SOL;
        var titulo = esClaro() ? 'Cambiar a tema oscuro' : 'Cambiar a tema claro';
        var flotante = document.getElementById('btn-tema');
        if (flotante) { flotante.innerHTML = icono; flotante.title = titulo; }
        var navs = document.querySelectorAll('.btn-tema-nav');
        for (var i = 0; i < navs.length; i++) {
            navs[i].innerHTML = icono;
            navs[i].title = titulo;
        }
    }

    function alternar() {
        var nuevo = esClaro() ? 'oscuro' : 'claro';
        document.documentElement.setAttribute('data-tema', nuevo);
        localStorage.setItem(CLAVE, nuevo);
        pintar();
    }

    function ligarBotones() {
        var navs = document.querySelectorAll('.btn-tema-nav');
        for (var i = 0; i < navs.length; i++) {
            if (!navs[i].dataset.temaLigado) {
                navs[i].dataset.temaLigado = '1';
                navs[i].addEventListener('click', alternar);
            }
        }
        if (navs.length > 0) return;
        if (document.getElementById('btn-tema')) return;
        var b = document.createElement('button');
        b.id = 'btn-tema';
        b.type = 'button';
        b.setAttribute('aria-label', 'Cambiar tema');
        b.addEventListener('click', alternar);
        document.body.appendChild(b);
    }

    function inicializar() {
        ligarBotones();
        pintar();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', inicializar);
    } else {
        inicializar();
    }
})();
