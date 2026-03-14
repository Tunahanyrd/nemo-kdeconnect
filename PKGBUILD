# Maintainer: JoeJoeTV <joejoetv@joejoetv.de>
# Co-Maintainer: Tunahanyrd <https://github.com/Tunahanyrd>

pkgname=nemo-kdeconnect
pkgver=1.3.0
pkgrel=1
pkgdesc='Nemo extension for KDE Connect file sharing and phone storage mounting (SFTP) with sidebar integration.'
arch=('any')
url="https://github.com/JoeJoeTV/nemo-extension-kdeconnect"
license=('GPL-3')
depends=('python' 'python-gobject' 'libnotify' 'nemo' 'kdeconnect' 'python-nemo')
makedepends=('gettext')
provides=('nemo-kdeconnect')
#sha256sums=('SKIP')

build() {
    # Compile localization files to .mo
    find "${srcdir}/nemo-kdeconnect/locale/" -name \*.po -print -execdir sh -c 'msgfmt -f -o "$(basename "$0" .po).mo" "$0"' '{}' \;
}

package() {
    install -D "${srcdir}/nemo-kdeconnect.py" "${pkgdir}/usr/share/nemo-python/extensions/nemo-kdeconnect.py"
    cd nemo-kdeconnect
    find "locale/" -type f -name \*.mo -print -exec install -D "${srcdir}/nemo-kdeconnect/{}" "${pkgdir}/usr/share/{}" \;
    cd ..
}
