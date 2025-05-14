Name:           rust
Version:        1.84.1
Release:        2%{?dist}
Summary:        The Rust Programming Language
License:        (Apache-2.0 OR MIT) AND (Artistic-2.0 AND BSD-3-Clause AND ISC AND MIT AND MPL-2.0 AND Unicode-DFS-2016)
# ^ written as: (rust itself) and (bundled libraries)
URL:            https://www.rust-lang.org

# Only x86_64, i686, and aarch64 are Tier 1 platforms at this time.
# https://doc.rust-lang.org/nightly/rustc/platform-support.html
%global rust_arches x86_64 i686 aarch64 ppc64le s390x
ExclusiveArch:  %{rust_arches}

# To bootstrap from scratch, set the channel and date from src/stage0.json
# e.g. 1.59.0 wants rustc: 1.58.0-2022-01-13
# or nightly wants some beta-YYYY-MM-DD
%global bootstrap_version 1.83.0
%global bootstrap_channel 1.83.0
%global bootstrap_date 2024-11-28

# Only the specified arches will use bootstrap binaries.
# NOTE: Those binaries used to be uploaded with every new release, but that was
# a waste of lookaside cache space when they're most often unused.
# Run "spectool -g rust.spec" after changing this and then "fedpkg upload" to
# add them to sources. Remember to remove them again after the bootstrap build!
#global bootstrap_arches %%{rust_arches}

# We need CRT files for *-wasi targets, at least as new as the commit in
# src/ci/docker/host-x86_64/dist-various-2/build-wasi-toolchain.sh
%global wasi_libc_url https://github.com/WebAssembly/wasi-libc
%global wasi_libc_ref wasi-sdk-25
%global wasi_libc_name wasi-libc-%{wasi_libc_ref}
%global wasi_libc_source %{wasi_libc_url}/archive/%{wasi_libc_ref}/%{wasi_libc_name}.tar.gz
%global wasi_libc_dir %{_builddir}/%{wasi_libc_name}
%if 0%{?fedora}
%bcond_with bundled_wasi_libc
%else
%bcond_without bundled_wasi_libc
%endif

# Using llvm-static may be helpful as an opt-in, e.g. to aid LLVM rebases.
%bcond_with llvm_static

# We can also choose to just use Rust's bundled LLVM, in case the system LLVM
# is insufficient.  Rust currently requires LLVM 18.0+.
%global min_llvm_version 18.0.0
%global bundled_llvm_version 19.1.5
#global llvm_compat_version 17
%global llvm llvm%{?llvm_compat_version}
%bcond_with bundled_llvm

# Requires stable libgit2 1.8, and not the next minor soname change.
# This needs to be consistent with the bindings in vendor/libgit2-sys.
%global min_libgit2_version 1.8.1
%global next_libgit2_version 1.9.0~
%global bundled_libgit2_version 1.8.1
%if 0%{?fedora} >= 41
%bcond_with bundled_libgit2
%else
%bcond_without bundled_libgit2
%endif

# Try to use system oniguruma (only used at build time for rust-docs)
# src/tools/rustbook -> ... -> onig_sys v69.8.1 needs at least 6.9.3
%global min_oniguruma_version 6.9.3
%if 0%{?rhel} && 0%{?rhel} < 9
%bcond_without bundled_oniguruma
%else
%bcond_with bundled_oniguruma
%endif

# Cargo uses UPSERTs with omitted conflict targets
%global min_sqlite3_version 3.35
%global bundled_sqlite3_version 3.46.0
%if 0%{?rhel} && 0%{?rhel} < 10
%bcond_without bundled_sqlite3
%else
%bcond_with bundled_sqlite3
%endif

%if 0%{?rhel}
# Disable cargo->libgit2->libssh2 on RHEL, as it's not approved for FIPS (rhbz1732949)
%bcond_without disabled_libssh2
%else
%bcond_with disabled_libssh2
%endif

# Reduce rustc's own debuginfo and optimizations to conserve 32-bit memory.
# e.g. https://github.com/rust-lang/rust/issues/45854
%global reduced_debuginfo 0
%if 0%{?__isa_bits} == 32
%global reduced_debuginfo 1
%endif
# Also on current riscv64 hardware, although future hardware will be
# able to handle it.
# e.g. http://fedora.riscv.rocks/koji/buildinfo?buildID=249870
%ifarch riscv64
%global reduced_debuginfo 1
%endif

%if 0%{?reduced_debuginfo}
%global enable_debuginfo --debuginfo-level=0 --debuginfo-level-std=2
%global enable_rust_opts --set rust.codegen-units-std=1
%bcond_with rustc_pgo
%else
# Build rustc with full debuginfo, CGU=1, ThinLTO, and PGO.
%global enable_debuginfo --debuginfo-level=2
%global enable_rust_opts --set rust.codegen-units=1 --set rust.lto=thin
%bcond_without rustc_pgo
%endif

# Detect non-stable channels from the version, like 1.74.0~beta.1
%{lua: do
  local version = rpm.expand("%{version}")
  local version_channel, subs = string.gsub(version, "^.*~(%w+).*$", "%1", 1)
  rpm.define("channel " .. (subs ~= 0 and version_channel or "stable"))
  rpm.define("rustc_package rustc-" .. version_channel .. "-src")
end}
Source0:        https://static.rust-lang.org/dist/%{rustc_package}.tar.xz
Source1:        %{wasi_libc_source}
# Sources for bootstrap_arches are inserted by lua below

# By default, rust tries to use "rust-lld" as a linker for some targets.
Patch1:         0001-Use-lld-provided-by-system.patch

# Set a substitute-path in rust-gdb for standard library sources.
Patch2:         rustc-1.70.0-rust-gdb-substitute-path.patch

# Override default target CPUs to match distro settings
# TODO: upstream this ability into the actual build configuration
Patch3:         0001-Let-environment-variables-override-some-default-CPUs.patch

# Override the default self-contained system libraries
# TODO: the first can probably be upstreamed, but the second is hard-coded,
# and we're only applying that if not with bundled_wasi_libc.
Patch4:         0001-bootstrap-allow-disabling-target-self-contained.patch
Patch5:         0002-set-an-external-library-path-for-wasm32-wasi.patch

# We don't want to use the bundled library in libsqlite3-sys
Patch6:         rustc-1.84.0-unbundle-sqlite.patch

# https://github.com/rust-lang/cc-rs/issues/1354
Patch7:         0001-Only-translate-profile-flags-for-Clang.patch

### RHEL-specific patches below ###

# Simple rpm macros for rust-toolset (as opposed to full rust-packaging)
Source100:      macros.rust-toolset
Source101:      cargo_vendor.attr
Source102:      cargo_vendor.prov

# Disable cargo->libgit2->libssh2 on RHEL, as it's not approved for FIPS (rhbz1732949)
Patch100:       rustc-1.84.0-disable-libssh2.patch

# Get the Rust triple for any architecture and ABI.
%{lua: function rust_triple(arch, abi)
  abi = abi or "gnu"
  if arch == "armv7hl" then
    arch = "armv7"
    abi = abi.."eabihf"
  elseif arch == "ppc64le" then
    arch = "powerpc64le"
  elseif arch == "riscv64" then
    arch = "riscv64gc"
  end
  return arch.."-unknown-linux-"..abi
end}

%define rust_triple() %{lua: print(rust_triple(
  rpm.expand("%{?1}%{!?1:%{_target_cpu}}"),
  rpm.expand("%{?2}%{!?2:gnu}")
))}

# Get the environment variable form of the Rust triple.
%define rust_triple_env() %{lua:
  print(rpm.expand("%{rust_triple %*}"):gsub("-", "_"):upper())
}

# Define a space-separated list of targets to ship rust-std-static-$triple for
# cross-compilation. The packages are noarch, but they're not fully
# reproducible between hosts, so only x86_64 actually builds it.
%ifarch x86_64
%if 0%{?fedora}
%global mingw_targets i686-pc-windows-gnu x86_64-pc-windows-gnu
%endif
%global wasm_targets wasm32-unknown-unknown wasm32-wasip1
%if 0%{?fedora}
%global extra_targets x86_64-unknown-none x86_64-unknown-uefi
%endif
%if 0%{?rhel} >= 10
%global extra_targets x86_64-unknown-none
%endif
%endif
%ifarch aarch64
%if 0%{?fedora}
%global extra_targets aarch64-unknown-none-softfloat aarch64-unknown-uefi
%endif
%if 0%{?rhel} >= 10
%global extra_targets aarch64-unknown-none-softfloat
%endif
%endif
%global all_targets %{?mingw_targets} %{?wasm_targets} %{?extra_targets}
%define target_enabled() %{lua:
  print(string.find(rpm.expand(" %{all_targets} "), rpm.expand(" %1 "), 1, true) or 0)
}

%if %defined bootstrap_arches
# For each bootstrap arch, add an additional binary Source.
# Also define bootstrap_source just for the current target.
%{lua: do
  local bootstrap_arches = {}
  for arch in string.gmatch(rpm.expand("%{bootstrap_arches}"), "%S+") do
    table.insert(bootstrap_arches, arch)
  end
  local base = rpm.expand("https://static.rust-lang.org/dist/%{bootstrap_date}")
  local channel = rpm.expand("%{bootstrap_channel}")
  local target_arch = rpm.expand("%{_target_cpu}")
  for i, arch in ipairs(bootstrap_arches) do
    i = 1000 + i * 3
    local suffix = channel.."-"..rust_triple(arch)
    print(string.format("Source%d: %s/cargo-%s.tar.xz\n", i, base, suffix))
    print(string.format("Source%d: %s/rustc-%s.tar.xz\n", i+1, base, suffix))
    print(string.format("Source%d: %s/rust-std-%s.tar.xz\n", i+2, base, suffix))
    if arch == target_arch then
      rpm.define("bootstrap_source_cargo "..i)
      rpm.define("bootstrap_source_rustc "..i+1)
      rpm.define("bootstrap_source_std "..i+2)
      rpm.define("bootstrap_suffix "..suffix)
    end
  end
end}
%endif

%ifarch %{bootstrap_arches}
%global local_rust_root %{_builddir}/rust-%{bootstrap_suffix}
Provides:       bundled(%{name}-bootstrap) = %{bootstrap_version}
%else
BuildRequires:  (cargo >= %{bootstrap_version} with cargo <= %{version})
BuildRequires:  (%{name} >= %{bootstrap_version} with %{name} <= %{version})
%global local_rust_root %{_prefix}
%endif

BuildRequires:  make
BuildRequires:  gcc-toolset-14-annobin-plugin-gcc
BuildRequires:  gcc-toolset-14-binutils
BuildRequires:  gcc-toolset-14-gcc
BuildRequires:  gcc-toolset-14-gcc-c++
BuildRequires:  ncurses-devel
# explicit curl-devel to avoid httpd24-curl (rhbz1540167)
BuildRequires:  curl-devel
BuildRequires:  pkgconfig(libcurl)
BuildRequires:  pkgconfig(liblzma)
BuildRequires:  pkgconfig(openssl)
BuildRequires:  pkgconfig(zlib)

%if %{without bundled_libgit2}
BuildRequires:  (pkgconfig(libgit2) >= %{min_libgit2_version} with pkgconfig(libgit2) < %{next_libgit2_version})
%endif

%if %{without bundled_oniguruma}
BuildRequires:  pkgconfig(oniguruma) >= %{min_oniguruma_version}
%endif

%if %{without bundled_sqlite3}
BuildRequires:  pkgconfig(sqlite3) >= %{min_sqlite3_version}
%endif

%if %{without disabled_libssh2}
BuildRequires:  pkgconfig(libssh2)
%endif

%if 0%{?rhel} == 8
BuildRequires:  platform-python
%else
BuildRequires:  python3
%endif
BuildRequires:  python3-rpm-macros

%if %with bundled_llvm
BuildRequires:  cmake >= 3.20.0
BuildRequires:  ninja-build
Provides:       bundled(llvm) = %{bundled_llvm_version}
%else
BuildRequires:  cmake >= 3.5.1
%if %defined llvm_compat_version
%global llvm_root %{_libdir}/%{llvm}
%else
%global llvm_root %{_prefix}
%endif
BuildRequires:  %{llvm}-devel >= %{min_llvm_version}
%if %with llvm_static
BuildRequires:  %{llvm}-static
BuildRequires:  libffi-devel
%endif
%endif

# make check needs "ps" for src/test/ui/wait-forked-but-failed-child.rs
BuildRequires:  procps-ng

# debuginfo-gdb tests need gdb
BuildRequires:  gdb

# For src/test/run-make/static-pie
BuildRequires:  glibc-static

# Virtual provides for folks who attempt "dnf install rustc"
Provides:       rustc = %{version}-%{release}
Provides:       rustc%{?_isa} = %{version}-%{release}

# Always require our exact standard library
Requires:       %{name}-std-static%{?_isa} = %{version}-%{release}

# The C compiler is needed at runtime just for linking.  Someday rustc might
# invoke the linker directly, and then we'll only need binutils.
# https://github.com/rust-lang/rust/issues/11937
Requires:       /usr/bin/cc

%global __ranlib %{_bindir}/ranlib

# ALL Rust libraries are private, because they don't keep an ABI.
%global _privatelibs lib(.*-[[:xdigit:]]{16}*|rustc.*)[.]so.*
%global __provides_exclude ^(%{_privatelibs})$
%global __requires_exclude ^(%{_privatelibs})$
%global __provides_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$
%global __requires_exclude_from ^(%{_docdir}|%{rustlibdir}/src)/.*$

# While we don't want to encourage dynamic linking to Rust shared libraries, as
# there's no stable ABI, we still need the unallocated metadata (.rustc) to
# support custom-derive plugins like #[proc_macro_derive(Foo)].
%global _find_debuginfo_opts --keep-section .rustc

# The standard library rlibs are essentially static archives, but we don't want
# to strip them because that impairs the debuginfo of all Rust programs.
# It also had a tendency to break the cross-compiled libraries:
# - wasm targets lost the archive index, which we were repairing with llvm-ranlib
# - uefi targets couldn't link builtins like memcpy, possibly due to lost COMDAT flags
%global __brp_strip_static_archive %{nil}
%global __brp_strip_lto %{nil}

%if %{without bundled_llvm}
%if "%{llvm_root}" == "%{_prefix}" || 0%{?scl:1}
%global llvm_has_filecheck 1
%endif
%endif

# We're going to override --libdir when configuring to get rustlib into a
# common path, but we'll fix the shared libraries during install.
%global common_libdir %{_prefix}/lib
%global rustlibdir %{common_libdir}/rustlib

%if %defined mingw_targets
BuildRequires:  mingw32-filesystem >= 95
BuildRequires:  mingw64-filesystem >= 95
BuildRequires:  mingw32-crt
BuildRequires:  mingw64-crt
BuildRequires:  mingw32-gcc
BuildRequires:  mingw64-gcc
BuildRequires:  mingw32-winpthreads-static
BuildRequires:  mingw64-winpthreads-static
%endif

%if %defined wasm_targets
%if %with bundled_wasi_libc
BuildRequires:  clang
%else
BuildRequires:  wasi-libc-static
%endif
BuildRequires:  lld
%endif

# For profiler_builtins
BuildRequires:  compiler-rt%{?llvm_compat_version}

# This component was removed as of Rust 1.69.0.
# https://github.com/rust-lang/rust/pull/101841
Obsoletes:      %{name}-analysis < 1.69.0~

%description
Rust is a systems programming language that runs blazingly fast, prevents
segfaults, and guarantees thread safety.

This package includes the Rust compiler and documentation generator.


%package std-static
Summary:        Standard library for Rust
Provides:       %{name}-std-static-%{rust_triple} = %{version}-%{release}
Requires:       %{name} = %{version}-%{release}
Requires:       glibc-devel%{?_isa} >= 2.17

%description std-static
This package includes the standard libraries for building applications
written in Rust.

%global target_package()                        \
%package std-static-%1                          \
Summary:        Standard library for Rust %1    \
Requires:       %{name} = %{version}-%{release}

%global target_description()                                            \
%description std-static-%1                                              \
This package includes the standard libraries for building applications  \
written in Rust for the %2 target %1.

%if %target_enabled i686-pc-windows-gnu
%target_package i686-pc-windows-gnu
Requires:       mingw32-crt
Requires:       mingw32-gcc
Requires:       mingw32-winpthreads-static
Provides:       mingw32-rust = %{version}-%{release}
Provides:       mingw32-rustc = %{version}-%{release}
BuildArch:      noarch
%target_description i686-pc-windows-gnu MinGW
%endif

%if %target_enabled x86_64-pc-windows-gnu
%target_package x86_64-pc-windows-gnu
Requires:       mingw64-crt
Requires:       mingw64-gcc
Requires:       mingw64-winpthreads-static
Provides:       mingw64-rust = %{version}-%{release}
Provides:       mingw64-rustc = %{version}-%{release}
BuildArch:      noarch
%target_description x86_64-pc-windows-gnu MinGW
%endif

%if %target_enabled wasm32-unknown-unknown
%target_package wasm32-unknown-unknown
Requires:       lld >= 8.0
BuildArch:      noarch
%target_description wasm32-unknown-unknown WebAssembly
%endif

%if %target_enabled wasm32-wasip1
%target_package wasm32-wasip1
Requires:       lld >= 8.0
%if %with bundled_wasi_libc
Provides:       bundled(wasi-libc)
%else
Requires:       wasi-libc-static
%endif
BuildArch:      noarch
# https://blog.rust-lang.org/2024/04/09/updates-to-rusts-wasi-targets.html
Obsoletes:      %{name}-std-static-wasm32-wasi < 1.84.0~
%target_description wasm32-wasip1 WebAssembly
%endif

%if %target_enabled x86_64-unknown-none
%target_package x86_64-unknown-none
Requires:       lld
%target_description x86_64-unknown-none embedded
%endif

%if %target_enabled aarch64-unknown-uefi
%target_package aarch64-unknown-uefi
Requires:       lld
%target_description aarch64-unknown-uefi embedded
%endif

%if %target_enabled x86_64-unknown-uefi
%target_package x86_64-unknown-uefi
Requires:       lld
%target_description x86_64-unknown-uefi embedded
%endif

%if %target_enabled aarch64-unknown-none-softfloat
%target_package aarch64-unknown-none-softfloat
Requires:       lld
%target_description aarch64-unknown-none-softfloat embedded
%endif


%package debugger-common
Summary:        Common debugger pretty printers for Rust
BuildArch:      noarch

%description debugger-common
This package includes the common functionality for %{name}-gdb and %{name}-lldb.


%package gdb
Summary:        GDB pretty printers for Rust
BuildArch:      noarch
Requires:       gdb
Requires:       %{name}-debugger-common = %{version}-%{release}

%description gdb
This package includes the rust-gdb script, which allows easier debugging of Rust
programs.


%package lldb
Summary:        LLDB pretty printers for Rust
BuildArch:      noarch
Requires:       lldb
Requires:       python3.12-lldb
Requires:       %{name}-debugger-common = %{version}-%{release}

%description lldb
This package includes the rust-lldb script, which allows easier debugging of Rust
programs.


%package doc
Summary:        Documentation for Rust
# NOT BuildArch:      noarch
# Note, while docs are mostly noarch, some things do vary by target_arch.
# Koji will fail the build in rpmdiff if two architectures build a noarch
# subpackage differently, so instead we have to keep its arch.

# Cargo no longer builds its own documentation
# https://github.com/rust-lang/cargo/pull/4904
# We used to keep a shim cargo-doc package, but now that's merged too.
Obsoletes:      cargo-doc < 1.65.0~
Provides:       cargo-doc = %{version}-%{release}

%description doc
This package includes HTML documentation for the Rust programming language and
its standard library.


%package -n cargo
Summary:        Rust's package manager and build tool
%if %with bundled_libgit2
Provides:       bundled(libgit2) = %{bundled_libgit2_version}
%endif
%if %with bundled_sqlite3
Provides:       bundled(sqlite) = %{bundled_sqlite3_version}
%endif
# For tests:
BuildRequires:  git-core
# Cargo is not much use without Rust
Requires:       %{name}

# "cargo vendor" is a builtin command starting with 1.37.  The Obsoletes and
# Provides are mostly relevant to RHEL, but harmless to have on Fedora/etc. too
Obsoletes:      cargo-vendor <= 0.1.23
Provides:       cargo-vendor = %{version}-%{release}

%description -n cargo
Cargo is a tool that allows Rust projects to declare their various dependencies
and ensure that you'll always get a repeatable build.


%package -n rustfmt
Summary:        Tool to find and fix Rust formatting issues
Requires:       cargo

# /usr/bin/rustfmt is dynamically linked against internal rustc libs
Requires:       %{name}%{?_isa} = %{version}-%{release}

# The component/package was rustfmt-preview until Rust 1.31.
Obsoletes:      rustfmt-preview < 1.0.0
Provides:       rustfmt-preview = %{version}-%{release}

%description -n rustfmt
A tool for formatting Rust code according to style guidelines.


%package analyzer
Summary:        Rust implementation of the Language Server Protocol

# /usr/bin/rust-analyzer is dynamically linked against internal rustc libs
Requires:       %{name}%{?_isa} = %{version}-%{release}

# The standard library sources are needed for most functionality.
Recommends:     %{name}-src

# RLS is no longer available as of Rust 1.65, but we're including the stub
# binary that implements LSP just enough to recommend rust-analyzer.
Obsoletes:      rls < 1.65.0~
# The component/package was rls-preview until Rust 1.31.
Obsoletes:      rls-preview < 1.31.6

%description analyzer
rust-analyzer is an implementation of Language Server Protocol for the Rust
programming language. It provides features like completion and goto definition
for many code editors, including VS Code, Emacs and Vim.


%package -n clippy
Summary:        Lints to catch common mistakes and improve your Rust code
Requires:       cargo
# /usr/bin/clippy-driver is dynamically linked against internal rustc libs
Requires:       %{name}%{?_isa} = %{version}-%{release}

# The component/package was clippy-preview until Rust 1.31.
Obsoletes:      clippy-preview <= 0.0.212
Provides:       clippy-preview = %{version}-%{release}

%description -n clippy
A collection of lints to catch common mistakes and improve your Rust code.


%package src
Summary:        Sources for the Rust standard library
BuildArch:      noarch
Recommends:     %{name}-std-static = %{version}-%{release}

%description src
This package includes source files for the Rust standard library.  It may be
useful as a reference for code completion tools in various editors.


%if 0%{?rhel}

%package toolset
Summary:        Rust Toolset
BuildArch:      noarch
Requires:       rust = %{version}-%{release}
Requires:       cargo = %{version}-%{release}

%description toolset
This is the metapackage for Rust Toolset, bringing in the Rust compiler,
the Cargo package manager, and a few convenience macros for rpm builds.

%endif


%prep

%ifarch %{bootstrap_arches}
rm -rf %{local_rust_root}
%setup -q -n cargo-%{bootstrap_suffix} -T -b %{bootstrap_source_cargo}
./install.sh --prefix=%{local_rust_root} --disable-ldconfig
%setup -q -n rustc-%{bootstrap_suffix} -T -b %{bootstrap_source_rustc}
./install.sh --prefix=%{local_rust_root} --disable-ldconfig
%setup -q -n rust-std-%{bootstrap_suffix} -T -b %{bootstrap_source_std}
./install.sh --prefix=%{local_rust_root} --disable-ldconfig
test -f '%{local_rust_root}/bin/cargo'
test -f '%{local_rust_root}/bin/rustc'
%endif

%if %{defined wasm_targets} && %{with bundled_wasi_libc}
%setup -q -n %{wasi_libc_name} -T -b 1
rm -rf %{wasi_libc_dir}/dlmalloc/
%endif

%setup -q -n %{rustc_package}

%patch -P1 -p1
%patch -P2 -p1
%patch -P3 -p1
%patch -P4 -p1
%if %without bundled_wasi_libc
%patch -P5 -p1
%endif
%if %without bundled_sqlite3
%patch -P6 -p1
%endif
%patch -P7 -p1 -d vendor/cc-1.2.5

%if %with disabled_libssh2
%patch -P100 -p1
%endif

# Use our explicit python3 first
sed -i.try-python -e '/^try python3 /i try "%{__python3}" "$@"' ./configure

# Set a substitute-path in rust-gdb for standard library sources.
sed -i.rust-src -e "s#@BUILDDIR@#$PWD#" ./src/etc/rust-gdb

%if %without bundled_llvm
rm -rf src/llvm-project/
mkdir -p src/llvm-project/libunwind/
%endif

# Remove submodules we don't need.
rm -rf src/gcc
rm -rf src/tools/enzyme
rm -rf src/tools/rustc-perf

# Remove other unused vendored libraries. This leaves the directory in place,
# because some build scripts watch them, e.g. "cargo:rerun-if-changed=curl".
%define clear_dir() find ./%1 -mindepth 1 -delete
%clear_dir vendor/curl-sys*/curl/
%clear_dir vendor/*jemalloc-sys*/jemalloc/
%clear_dir vendor/libffi-sys*/libffi/
%clear_dir vendor/libmimalloc-sys*/c_src/mimalloc/
%clear_dir vendor/libsqlite3-sys*/sqlcipher/
%clear_dir vendor/libssh2-sys*/libssh2/
%clear_dir vendor/libz-sys*/src/zlib{,-ng}/
%clear_dir vendor/lzma-sys*/xz-*/
%clear_dir vendor/openssl-src*/openssl/

%if %without bundled_libgit2
%clear_dir vendor/libgit2-sys*/libgit2/
%endif

%if %without bundled_oniguruma
%clear_dir vendor/onig_sys*/oniguruma/
%endif

%if %without bundled_sqlite3
%clear_dir vendor/libsqlite3-sys*/sqlite3/
%endif

%if %with disabled_libssh2
rm -rf vendor/libssh2-sys*/
%endif

# This only affects the transient rust-installer, but let it use our dynamic xz-libs
sed -i.lzma -e '/LZMA_API_STATIC/d' src/bootstrap/src/core/build_steps/tool.rs

%if %{without bundled_llvm} && %{with llvm_static}
# Static linking to distro LLVM needs to add -lffi
# https://github.com/rust-lang/rust/issues/34486
sed -i.ffi -e '$a #[link(name = "ffi")] extern {}' \
  compiler/rustc_llvm/src/lib.rs
%endif

# The configure macro will modify some autoconf-related files, which upsets
# cargo when it tries to verify checksums in those files.  If we just truncate
# that file list, cargo won't have anything to complain about.
find vendor -name .cargo-checksum.json \
  -exec sed -i.uncheck -e 's/"files":{[^}]*}/"files":{ }/' '{}' '+'

# Sometimes Rust sources start with #![...] attributes, and "smart" editors think
# it's a shebang and make them executable. Then brp-mangle-shebangs gets upset...
find -name '*.rs' -type f -perm /111 -exec chmod -v -x '{}' '+'

# The distro flags are only appropriate for the host, not our cross-targets,
# and they're not as fine-grained as the settings we choose for std vs rustc.
%if %defined build_rustflags
%global build_rustflags %{nil}
%endif

# These are similar to __cflags_arch_* in /usr/lib/rpm/redhat/macros
%global rustc_target_cpus %{lua: do
  local fedora = tonumber(rpm.expand("0%{?fedora}"))
  local rhel = tonumber(rpm.expand("0%{?rhel}"))
  local env =
    " RUSTC_TARGET_CPU_X86_64=x86-64" .. ((rhel >= 10) and "-v3" or (rhel == 9) and "-v2" or "")
    .. " RUSTC_TARGET_CPU_PPC64LE=" .. ((rhel >= 9) and "pwr9" or "pwr8")
    .. " RUSTC_TARGET_CPU_S390X=" ..
        ((rhel >= 9) and "z14" or (rhel == 8 or fedora >= 38) and "z13" or
         (fedora >= 26) and "zEC12" or (rhel == 7) and "z196" or "z10")
  print(env)
end}

# Set up shared environment variables for build/install/check.
# *_USE_PKG_CONFIG=1 convinces *-sys crates to use the system library.
%global rust_env %{shrink:
  %{?rustflags:RUSTFLAGS="%{rustflags}"}
  %{rustc_target_cpus}
  %{!?with_bundled_oniguruma:RUSTONIG_SYSTEM_LIBONIG=1}
  %{!?with_bundled_sqlite3:LIBSQLITE3_SYS_USE_PKG_CONFIG=1}
  %{!?with_disabled_libssh2:LIBSSH2_SYS_USE_PKG_CONFIG=1}
}
%global export_rust_env export %{rust_env} ; source /opt/rh/gcc-toolset-14/enable

%build
%{export_rust_env}

# Some builders have relatively little memory for their CPU count.
# At least 4GB per CPU is a good rule of thumb for building rustc.
%if ! %defined constrain_build
%define constrain_build(m:) %{lua:
  for l in io.lines('/proc/meminfo') do
    if l:sub(1, 9) == "MemTotal:" then
      local opt_m = math.tointeger(rpm.expand("%{-m*}"))
      local mem_total = math.tointeger(string.match(l, "MemTotal:%s+(%d+)"))
      local cpu_limit = math.max(1, mem_total // (opt_m * 1024))
      if cpu_limit < math.tointeger(rpm.expand("%_smp_build_ncpus")) then
        rpm.define("_smp_build_ncpus " .. cpu_limit)
      end
      break
    end
  end
}
%endif
%constrain_build -m 4096

%if %defined mingw_targets
%define mingw_target_config %{shrink:
  --set target.i686-pc-windows-gnu.linker=%{mingw32_cc}
  --set target.i686-pc-windows-gnu.cc=%{mingw32_cc}
  --set target.i686-pc-windows-gnu.ar=%{mingw32_ar}
  --set target.i686-pc-windows-gnu.ranlib=%{mingw32_ranlib}
  --set target.i686-pc-windows-gnu.self-contained=false
  --set target.x86_64-pc-windows-gnu.linker=%{mingw64_cc}
  --set target.x86_64-pc-windows-gnu.cc=%{mingw64_cc}
  --set target.x86_64-pc-windows-gnu.ar=%{mingw64_ar}
  --set target.x86_64-pc-windows-gnu.ranlib=%{mingw64_ranlib}
  --set target.x86_64-pc-windows-gnu.self-contained=false
}
%endif

%if %defined wasm_targets
%if %with bundled_wasi_libc
%define wasi_libc_flags MALLOC_IMPL=emmalloc CC=clang AR=llvm-ar NM=llvm-nm
%make_build --quiet -C %{wasi_libc_dir} %{wasi_libc_flags} TARGET_TRIPLE=wasm32-wasip1
%define wasm_target_config %{shrink:
  --set target.wasm32-wasip1.wasi-root=%{wasi_libc_dir}/sysroot
}
%else
%define wasm_target_config %{shrink:
  --set target.wasm32-wasip1.wasi-root=%{_prefix}/wasm32-wasi
  --set target.wasm32-wasip1.self-contained=false
}
%endif
%endif

# Find the compiler-rt library for the Rust profiler_builtins crate.
%if %defined llvm_compat_version
# clang_resource_dir is not defined for compat builds.
%define profiler /usr/lib/clang/%{llvm_compat_version}/lib/%{_arch}-redhat-linux-gnu/libclang_rt.profile.a
%else
%define profiler %{clang_resource_dir}/lib/%{_arch}-redhat-linux-gnu/libclang_rt.profile.a
%endif
test -r "%{profiler}"

%configure --disable-option-checking \
  --docdir=%{_pkgdocdir} \
  --libdir=%{common_libdir} \
  --build=%{rust_triple} --host=%{rust_triple} --target=%{rust_triple} \
  --set target.%{rust_triple}.linker=%{__cc} \
  --set target.%{rust_triple}.cc=%{__cc} \
  --set target.%{rust_triple}.cxx=%{__cxx} \
  --set target.%{rust_triple}.ar=%{__ar} \
  --set target.%{rust_triple}.ranlib=%{__ranlib} \
  --set target.%{rust_triple}.profiler="%{profiler}" \
  %{?mingw_target_config} \
  %{?wasm_target_config} \
  --python=%{__python3} \
  --local-rust-root=%{local_rust_root} \
  --set build.rustfmt=/bin/true \
  %{!?with_bundled_llvm: --llvm-root=%{llvm_root} \
    %{!?llvm_has_filecheck: --disable-codegen-tests} \
    %{!?with_llvm_static: --enable-llvm-link-shared } } \
  --disable-llvm-static-stdcpp \
  --disable-llvm-bitcode-linker \
  --disable-lld \
  --disable-rpath \
  %{enable_debuginfo} \
  %{enable_rust_opts} \
  --set build.jobs=%_smp_build_ncpus \
  --set build.build-stage=2 \
  --set build.doc-stage=2 \
  --set build.install-stage=2 \
  --set build.test-stage=2 \
  --set build.optimized-compiler-builtins=false \
  --set rust.llvm-tools=false \
  --enable-extended \
  --tools=cargo,clippy,rls,rust-analyzer,rustfmt,src \
  --enable-vendor \
  --enable-verbose-tests \
  --release-channel=%{channel} \
  --release-description="%{?fedora:Fedora }%{?rhel:Red Hat }%{version}-%{release}"

%global __x %{__python3} ./x.py

%if %with rustc_pgo
# Build the compiler with profile instrumentation
%define profraw $PWD/build/profiles
%define profdata $PWD/build/rustc.profdata
mkdir -p "%{profraw}"
%{__x} build sysroot --rust-profile-generate="%{profraw}"
# Build cargo as a workload to generate compiler profiles
env LLVM_PROFILE_FILE="%{profraw}/default_%%m_%%p.profraw" \
  %{__x} --keep-stage=0 --keep-stage=1 build cargo
# Finalize the profile data and clean up the raw files
%{llvm_root}/bin/llvm-profdata merge -o "%{profdata}" "%{profraw}"
rm -r "%{profraw}" build/%{rust_triple}/stage2*/
# Redefine the macro to use that profile data from now on
%global __x %{__x} --rust-profile-use="%{profdata}"
%endif

# Build the compiler normally (with or without PGO)
%{__x} build sysroot

# Build everything else normally
%{__x} build
%{__x} doc

for triple in %{?all_targets} ; do
  %{__x} build --target=$triple std
done

%install
%if 0%{?rhel} && 0%{?rhel} <= 9
%{?set_build_flags}
%endif
%{export_rust_env}

DESTDIR=%{buildroot} %{__x} install

for triple in %{?all_targets} ; do
  DESTDIR=%{buildroot} %{__x} install --target=$triple std
done

# The rls stub doesn't have an install target, but we can just copy it.
%{__install} -t %{buildroot}%{_bindir} build/%{rust_triple}/stage2-tools-bin/rls

# These are transient files used by x.py dist and install
rm -rf ./build/dist/ ./build/tmp/

# Some of the components duplicate-install binaries, leaving backups we don't want
rm -f %{buildroot}%{_bindir}/*.old

# Make sure the compiler's shared libraries are in the proper libdir
%if "%{_libdir}" != "%{common_libdir}"
mkdir -p %{buildroot}%{_libdir}
find %{buildroot}%{common_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec mv -v -t %{buildroot}%{_libdir} '{}' '+'
%endif

# The shared libraries should be executable for debuginfo extraction.
find %{buildroot}%{_libdir} -maxdepth 1 -type f -name '*.so' \
  -exec chmod -v +x '{}' '+'

# The shared standard library is excluded from Provides, because it has no
# stable ABI. However, we still ship it alongside the static target libraries
# to enable some niche local use-cases, like the `evcxr` REPL.
# Make sure those libraries are also executable for debuginfo extraction.
find %{buildroot}%{rustlibdir} -type f -name '*.so' \
  -exec chmod -v +x '{}' '+'

# Remove installer artifacts (manifests, uninstall scripts, etc.)
find %{buildroot}%{rustlibdir} -maxdepth 1 -type f -exec rm -v '{}' '+'

# Remove backup files from %%configure munging
find %{buildroot}%{rustlibdir} -type f -name '*.orig' -exec rm -v '{}' '+'

# https://fedoraproject.org/wiki/Changes/Make_ambiguous_python_shebangs_error
# We don't actually need to ship any of those python scripts in rust-src anyway.
find %{buildroot}%{rustlibdir}/src -type f -name '*.py' -exec rm -v '{}' '+'

# Remove unwanted documentation files (we already package them)
rm -f %{buildroot}%{_pkgdocdir}/README.md
rm -f %{buildroot}%{_pkgdocdir}/COPYRIGHT
rm -f %{buildroot}%{_pkgdocdir}/LICENSE
rm -f %{buildroot}%{_pkgdocdir}/LICENSE-APACHE
rm -f %{buildroot}%{_pkgdocdir}/LICENSE-MIT
rm -f %{buildroot}%{_pkgdocdir}/LICENSE-THIRD-PARTY
rm -f %{buildroot}%{_pkgdocdir}/*.old

# Sanitize the HTML documentation
find %{buildroot}%{_pkgdocdir}/html -empty -delete
find %{buildroot}%{_pkgdocdir}/html -type f -exec chmod -x '{}' '+'

# Create the path for crate-devel packages
mkdir -p %{buildroot}%{_datadir}/cargo/registry

# Cargo no longer builds its own documentation
# https://github.com/rust-lang/cargo/pull/4904
mkdir -p %{buildroot}%{_docdir}/cargo
ln -sT ../rust/html/cargo/ %{buildroot}%{_docdir}/cargo/html

# We don't want Rust copies of LLVM tools (rust-lld, rust-llvm-dwp)
rm -f %{buildroot}%{rustlibdir}/%{rust_triple}/bin/rust-ll*

%if 0%{?rhel}
# This allows users to build packages using Rust Toolset.
%{__install} -D -m 644 %{S:100} %{buildroot}%{rpmmacrodir}/macros.rust-toolset
%{__install} -D -m 644 %{S:101} %{buildroot}%{_fileattrsdir}/cargo_vendor.attr
%{__install} -D -m 755 %{S:102} %{buildroot}%{_rpmconfigdir}/cargo_vendor.prov
%endif


%check
%if 0%{?rhel} && 0%{?rhel} <= 9
%{?set_build_flags}
%endif
%{export_rust_env}

# Sanity-check the installed binaries, debuginfo-stripped and all.
TMP_HELLO=$(mktemp -d)
(
  cd "$TMP_HELLO"
  export RUSTC=%{buildroot}%{_bindir}/rustc \
    LD_LIBRARY_PATH="%{buildroot}%{_libdir}:$LD_LIBRARY_PATH"
  %{buildroot}%{_bindir}/cargo init --name hello-world
  %{buildroot}%{_bindir}/cargo run --verbose

  # Sanity-check that code-coverage builds and runs
  env RUSTFLAGS="-Cinstrument-coverage" %{buildroot}%{_bindir}/cargo run --verbose
  test -r default_*.profraw

  # Try a build sanity-check for other std-enabled targets
  for triple in %{?mingw_targets} %{?wasm_targets}; do
    %{buildroot}%{_bindir}/cargo build --verbose --target=$triple
  done
)
rm -rf "$TMP_HELLO"

# The results are not stable on koji, so mask errors and just log it.
# Some of the larger test artifacts are manually cleaned to save space.

# - Bootstrap is excluded because it's not something we ship, and a lot of its
#   tests are geared toward the upstream CI environment.
# - Crashes are excluded because they are less reliable, especially stuff like
#   SIGSEGV across different arches -- UB can do all kinds of weird things.
#   They're only meant to notice "accidental" fixes anyway, not *should* crash.
timeout -v 90m %{__x} test --no-fail-fast --skip={src/bootstrap,tests/crashes} || :
rm -rf "./build/%{rust_triple}/test/"

%ifarch aarch64
# https://github.com/rust-lang/rust/issues/123733
%define cargo_test_skip --test-args "--skip panic_abort_doc_tests"
%endif
timeout -v 30m %{__x} test --no-fail-fast cargo %{?cargo_test_skip} || :
rm -rf "./build/%{rust_triple}/stage2-tools/%{rust_triple}/cit/"

timeout -v 30m %{__x} test --no-fail-fast clippy || :

timeout -v 30m %{__x} test --no-fail-fast rust-analyzer || :

timeout -v 30m %{__x} test --no-fail-fast rustfmt || :


%ldconfig_scriptlets


%files
%license COPYRIGHT LICENSE-APACHE LICENSE-MIT
%doc README.md
%{_bindir}/rustc
%{_bindir}/rustdoc
%{_libdir}/librustc_driver-*.so
%{_libexecdir}/rust-analyzer-proc-macro-srv
%{_mandir}/man1/rustc.1*
%{_mandir}/man1/rustdoc.1*


%files std-static
%dir %{rustlibdir}
%dir %{rustlibdir}/%{rust_triple}
%dir %{rustlibdir}/%{rust_triple}/lib
%{rustlibdir}/%{rust_triple}/lib/*.rlib
%{rustlibdir}/%{rust_triple}/lib/*.so

%global target_files()      \
%files std-static-%1        \
%dir %{rustlibdir}          \
%dir %{rustlibdir}/%1       \
%dir %{rustlibdir}/%1/lib   \
%{rustlibdir}/%1/lib/*.rlib

%if %target_enabled i686-pc-windows-gnu
%target_files i686-pc-windows-gnu
%{rustlibdir}/i686-pc-windows-gnu/lib/rs*.o
%exclude %{rustlibdir}/i686-pc-windows-gnu/lib/*.dll
%exclude %{rustlibdir}/i686-pc-windows-gnu/lib/*.dll.a
%endif

%if %target_enabled x86_64-pc-windows-gnu
%target_files x86_64-pc-windows-gnu
%{rustlibdir}/x86_64-pc-windows-gnu/lib/rs*.o
%exclude %{rustlibdir}/x86_64-pc-windows-gnu/lib/*.dll
%exclude %{rustlibdir}/x86_64-pc-windows-gnu/lib/*.dll.a
%endif

%if %target_enabled wasm32-unknown-unknown
%target_files wasm32-unknown-unknown
%endif

%if %target_enabled wasm32-wasip1
%target_files wasm32-wasip1
%if %with bundled_wasi_libc
%dir %{rustlibdir}/wasm32-wasip1/lib/self-contained
%{rustlibdir}/wasm32-wasip1/lib/self-contained/crt*.o
%{rustlibdir}/wasm32-wasip1/lib/self-contained/libc.a
%endif
%endif

%if %target_enabled x86_64-unknown-none
%target_files x86_64-unknown-none
%endif

%if %target_enabled aarch64-unknown-uefi
%target_files aarch64-unknown-uefi
%endif

%if %target_enabled x86_64-unknown-uefi
%target_files x86_64-unknown-uefi
%endif

%if %target_enabled aarch64-unknown-none-softfloat
%target_files aarch64-unknown-none-softfloat
%endif


%files debugger-common
%dir %{rustlibdir}
%dir %{rustlibdir}/etc
%{rustlibdir}/etc/rust_*.py*


%files gdb
%{_bindir}/rust-gdb
%{rustlibdir}/etc/gdb_*
%exclude %{_bindir}/rust-gdbgui


%files lldb
%{_bindir}/rust-lldb
%{rustlibdir}/etc/lldb_*


%files doc
%docdir %{_pkgdocdir}
%dir %{_pkgdocdir}
%{_pkgdocdir}/html
# former cargo-doc
%docdir %{_docdir}/cargo
%dir %{_docdir}/cargo
%{_docdir}/cargo/html


%files -n cargo
%license src/tools/cargo/LICENSE-{APACHE,MIT,THIRD-PARTY}
%doc src/tools/cargo/README.md
%{_bindir}/cargo
%{_mandir}/man1/cargo*.1*
%{_sysconfdir}/bash_completion.d/cargo
%{_datadir}/zsh/site-functions/_cargo
%dir %{_datadir}/cargo
%dir %{_datadir}/cargo/registry


%files -n rustfmt
%{_bindir}/rustfmt
%{_bindir}/cargo-fmt
%doc src/tools/rustfmt/{README,CHANGELOG,Configurations}.md
%license src/tools/rustfmt/LICENSE-{APACHE,MIT}


%files analyzer
%{_bindir}/rls
%{_bindir}/rust-analyzer
%doc src/tools/rust-analyzer/README.md
%license src/tools/rust-analyzer/LICENSE-{APACHE,MIT}


%files -n clippy
%{_bindir}/cargo-clippy
%{_bindir}/clippy-driver
%doc src/tools/clippy/{README.md,CHANGELOG.md}
%license src/tools/clippy/LICENSE-{APACHE,MIT}


%files src
%dir %{rustlibdir}
%{rustlibdir}/src


%if 0%{?rhel}
%files toolset
%{rpmmacrodir}/macros.rust-toolset
%{_fileattrsdir}/cargo_vendor.attr
%{_rpmconfigdir}/cargo_vendor.prov
%endif


%changelog
* Mon Apr 28 2025 Josh Stone <jistone@redhat.com> - 1.84.1-2
- Use python3.12 prefix for lldb Requires

* Tue Feb 04 2025 Josh Stone <jistone@redhat.com> - 1.84.1-1
- Update to 1.84.1

* Wed Jan 15 2025 Josh Stone <jistone@redhat.com> - 1.84.0-1
- Update to 1.84.0

* Thu Dec 05 2024 Josh Stone <jistone@redhat.com> - 1.83.0-1
- Update to 1.83.0
- Remove the subshell in the cargo_install macro

* Tue Nov 05 2024 Josh Stone <jistone@redhat.com> - 1.82.0-1
- Update to 1.82.0

* Fri Oct 25 2024 Josh Stone <jistone@redhat.com> - 1.81.0-1
- Update to 1.81.0

* Tue Oct 22 2024 Josh Stone <jistone@redhat.com> - 1.80.1-1
- Update to 1.80.1

* Tue Aug 13 2024 Josh Stone <jistone@redhat.com> - 1.79.0-2
- Disable jump threading of float equality

* Fri Jun 21 2024 Josh Stone <jistone@redhat.com> - 1.79.0-1
- Update to 1.79.0

* Fri Jun 21 2024 Josh Stone <jistone@redhat.com> - 1.78.0-1
- Update to 1.78.0
- Make std-static-wasm* noarch again

* Thu May 09 2024 Josh Stone <jistone@redhat.com> - 1.77.2-1
- Update to 1.77.2.

* Wed Apr 17 2024 Josh Stone <jistone@redhat.com> - 1.76.0-1
- Update to 1.76.0.
- Sync rust-toolset macros to rust-packaging v25.2

* Fri Jan 05 2024 Josh Stone <jistone@redhat.com> - 1.75.0-1
- Update to 1.75.0.

* Wed Jan 03 2024 Josh Stone <jistone@redhat.com> - 1.74.1-1
- Update to 1.74.1.

* Tue Oct 17 2023 Josh Stone <jistone@redhat.com> - 1.73.0-1
- Update to 1.73.0.
- Use emmalloc instead of CC0 dlmalloc when bundling wasi-libc

* Thu Oct 12 2023 Josh Stone <jistone@redhat.com> - 1.72.1-1
- Update to 1.72.1.
- Migrated to SPDX license

* Tue Aug 08 2023 Josh Stone <jistone@redhat.com> - 1.71.1-1
- Update to 1.71.1.
- Security fix for CVE-2023-38497

* Wed Jul 26 2023 Josh Stone <jistone@redhat.com> - 1.71.0-2
- Relax the suspicious_double_ref_op lint (rhbz2225471)
- Enable the profiler runtime for native hosts (rhbz2213875)

* Thu Jul 20 2023 Josh Stone <jistone@redhat.com> - 1.71.0-1
- Update to 1.71.0.

* Tue Jul 18 2023 Josh Stone <jistone@redhat.com> - 1.70.0-1
- Update to 1.70.0.

* Fri May 26 2023 Josh Stone <jistone@redhat.com> - 1.69.0-1
- Update to 1.69.0.
- Obsolete rust-analysis.

* Fri May 19 2023 Josh Stone <jistone@redhat.com> - 1.68.2-1
- Update to 1.68.2.

* Thu May 18 2023 Josh Stone <jistone@redhat.com> - 1.67.1-1
- Update to 1.67.1.

* Wed Jan 11 2023 Josh Stone <jistone@redhat.com> - 1.66.1-1
- Update to 1.66.1.

* Fri Jan 06 2023 Josh Stone <jistone@redhat.com> - 1.65.0-1
- Update to 1.65.0.
- rust-analyzer now obsoletes rls.

* Thu Sep 22 2022 Josh Stone <jistone@redhat.com> - 1.64.0-1
- Update to 1.64.0.
- Add rust-analyzer.

* Wed Sep 07 2022 Josh Stone <jistone@redhat.com> - 1.63.0-1
- Update to 1.63.0.

* Tue Jul 19 2022 Josh Stone <jistone@redhat.com> - 1.62.1-1
- Update to 1.62.1.

* Wed Jul 13 2022 Josh Stone <jistone@redhat.com> - 1.62.0-2
- Prevent unsound coercions from functions with opaque return types.

* Thu Jun 30 2022 Josh Stone <jistone@redhat.com> - 1.62.0-1
- Update to 1.62.0.

* Fri Jun 03 2022 Josh Stone <jistone@redhat.com> - 1.61.0-1
- Update to 1.61.0.
- Add rust-toolset as a subpackage.

* Wed Apr 20 2022 Josh Stone <jistone@redhat.com> - 1.60.0-1
- Update to 1.60.0.

* Tue Apr 19 2022 Josh Stone <jistone@redhat.com> - 1.59.0-1
- Update to 1.59.0.

* Thu Jan 20 2022 Josh Stone <jistone@redhat.com> - 1.58.1-1
- Update to 1.58.1.

* Thu Jan 13 2022 Josh Stone <jistone@redhat.com> - 1.58.0-1
- Update to 1.58.0.

* Wed Dec 15 2021 Josh Stone <jistone@redhat.com> - 1.57.0-1
- Update to 1.57.0.

* Thu Dec 02 2021 Josh Stone <jistone@redhat.com> - 1.56.1-2
- Add rust-std-static-wasm32-wasi
  Resolves: rhbz#1980080

* Tue Nov 02 2021 Josh Stone <jistone@redhat.com> - 1.56.0-1
- Update to 1.56.1.

* Fri Oct 29 2021 Josh Stone <jistone@redhat.com> - 1.55.0-1
- Update to 1.55.0.
- Backport support for LLVM 13.

* Tue Aug 17 2021 Josh Stone <jistone@redhat.com> - 1.54.0-2
- Make std-static-wasm* arch-specific to avoid s390x.

* Thu Jul 29 2021 Josh Stone <jistone@redhat.com> - 1.54.0-1
- Update to 1.54.0.

* Tue Jul 20 2021 Josh Stone <jistone@redhat.com> - 1.53.0-2
- Use llvm-ranlib to fix wasm archives.

* Mon Jun 21 2021 Josh Stone <jistone@redhat.com> - 1.53.0-1
- Update to 1.53.0.

* Tue Jun 15 2021 Josh Stone <jistone@redhat.com> - 1.52.1-2
- Set rust.codegen-units-std=1 for all targets again.
- Add rust-std-static-wasm32-unknown-unknown.

* Tue May 25 2021 Josh Stone <jistone@redhat.com> - 1.52.1-1
- Update to 1.52.1. Includes security fixes for CVE-2020-36323,
  CVE-2021-28876, CVE-2021-28878, CVE-2021-28879, and CVE-2021-31162.

* Mon May 24 2021 Josh Stone <jistone@redhat.com> - 1.51.0-1
- Update to 1.51.0. Update to 1.51.0. Includes security fixes for
  CVE-2021-28875 and CVE-2021-28877.

* Mon May 24 2021 Josh Stone <jistone@redhat.com> - 1.50.0-1
- Update to 1.50.0.

* Wed Jan 13 2021 Josh Stone <jistone@redhat.com> - 1.49.0-1
- Update to 1.49.0.

* Tue Jan 12 2021 Josh Stone <jistone@redhat.com> - 1.48.0-1
- Update to 1.48.0.

* Thu Oct 22 2020 Josh Stone <jistone@redhat.com> - 1.47.0-1
- Update to 1.47.0.

* Wed Oct 14 2020 Josh Stone <jistone@redhat.com> - 1.46.0-1
- Update to 1.46.0.

* Tue Aug 04 2020 Josh Stone <jistone@redhat.com> - 1.45.2-1
- Update to 1.45.2.

* Thu Jul 16 2020 Josh Stone <jistone@redhat.com> - 1.45.0-1
- Update to 1.45.0.

* Tue Jul 14 2020 Josh Stone <jistone@redhat.com> - 1.44.1-1
- Update to 1.44.1.

* Thu May 07 2020 Josh Stone <jistone@redhat.com> - 1.43.1-1
- Update to 1.43.1.

* Thu Apr 23 2020 Josh Stone <jistone@redhat.com> - 1.43.0-1
- Update to 1.43.0.

* Thu Mar 12 2020 Josh Stone <jistone@redhat.com> - 1.42.0-1
- Update to 1.42.0.

* Thu Feb 27 2020 Josh Stone <jistone@redhat.com> - 1.41.1-1
- Update to 1.41.1.

* Thu Jan 30 2020 Josh Stone <jistone@redhat.com> - 1.41.0-1
- Update to 1.41.0.

* Thu Jan 16 2020 Josh Stone <jistone@redhat.com> - 1.40.0-1
- Update to 1.40.0.
- Fix compiletest with newer (local-rebuild) libtest
- Build compiletest with in-tree libtest
- Fix ARM EHABI unwinding

* Tue Nov 12 2019 Josh Stone <jistone@redhat.com> - 1.39.0-2
- Fix a couple build and test issues with rustdoc.

* Thu Nov 07 2019 Josh Stone <jistone@redhat.com> - 1.39.0-1
- Update to 1.39.0.

* Thu Sep 26 2019 Josh Stone <jistone@redhat.com> - 1.38.0-1
- Update to 1.38.0.

* Thu Aug 15 2019 Josh Stone <jistone@redhat.com> - 1.37.0-1
- Update to 1.37.0.
- Disable libssh2 (git+ssh support).

* Thu Jul 04 2019 Josh Stone <jistone@redhat.com> - 1.36.0-1
- Update to 1.36.0.

* Wed May 29 2019 Josh Stone <jistone@redhat.com> - 1.35.0-2
- Fix compiletest for rebuild testing.

* Thu May 23 2019 Josh Stone <jistone@redhat.com> - 1.35.0-1
- Update to 1.35.0.

* Tue May 14 2019 Josh Stone <jistone@redhat.com> - 1.34.2-1
- Update to 1.34.2 -- fixes CVE-2019-12083.

* Thu May 09 2019 Josh Stone <jistone@redhat.com> - 1.34.1-1
- Update to 1.34.1.

* Thu Apr 11 2019 Josh Stone <jistone@redhat.com> - 1.34.0-1
- Update to 1.34.0.

* Wed Apr 10 2019 Josh Stone <jistone@redhat.com> - 1.33.0-1
- Update to 1.33.0.

* Tue Apr 09 2019 Josh Stone <jistone@redhat.com> - 1.32.0-1
- Update to 1.32.0.

* Fri Dec 14 2018 Josh Stone <jistone@redhat.com> - 1.31.0-5
- Restore rust-lldb.

* Thu Dec 13 2018 Josh Stone <jistone@redhat.com> - 1.31.0-4
- Backport fixes for rls.

* Thu Dec 13 2018 Josh Stone <jistone@redhat.com> - 1.31.0-3
- Update to 1.31.0 -- Rust 2018!
- clippy/rls/rustfmt are no longer -preview

* Wed Dec 12 2018 Josh Stone <jistone@redhat.com> - 1.30.1-2
- Update to 1.30.1.

* Tue Nov 06 2018 Josh Stone <jistone@redhat.com> - 1.29.2-1
- Update to 1.29.2.

* Thu Nov 01 2018 Josh Stone <jistone@redhat.com> - 1.28.0-1
- Update to 1.28.0.

* Thu Nov 01 2018 Josh Stone <jistone@redhat.com> - 1.27.2-1
- Update to 1.27.2.

* Wed Oct 10 2018 Josh Stone <jistone@redhat.com> - 1.26.2-12
- Fix "fp" target feature for AArch64 (#1632880)

* Mon Oct 08 2018 Josh Stone <jistone@redhat.com> - 1.26.2-11
- Security fix for str::repeat (pending CVE).

* Fri Oct 05 2018 Josh Stone <jistone@redhat.com> - 1.26.2-10
- Rebuild without bootstrap binaries.

* Thu Oct 04 2018 Josh Stone <jistone@redhat.com> - 1.26.2-9
- Bootstrap without SCL packaging. (rhbz1635067)

* Tue Aug 28 2018 Tom Stellard <tstellar@redhat.com> - 1.26.2-8
- Use python3 prefix for lldb Requires

* Mon Aug 13 2018 Josh Stone <jistone@redhat.com> - 1.26.2-7
- Build with platform-python

* Tue Aug 07 2018 Josh Stone <jistone@redhat.com> - 1.26.2-6
- Exclude rust-src from auto-requires

* Thu Aug 02 2018 Josh Stone <jistone@redhat.com> - 1.26.2-5
- Rebuild without bootstrap binaries.

* Tue Jul 31 2018 Josh Stone <jistone@redhat.com> - 1.26.2-4
- Bootstrap as a module.

* Mon Jun 04 2018 Josh Stone <jistone@redhat.com> - 1.26.2-3
- Update to 1.26.2.

* Wed May 30 2018 Josh Stone <jistone@redhat.com> - 1.26.1-2
- Update to 1.26.1.

* Fri May 18 2018 Josh Stone <jistone@redhat.com> - 1.26.0-1
- Update to 1.26.0.

* Tue Apr 10 2018 Josh Stone <jistone@redhat.com> - 1.25.0-2
- Filter codegen-backends from Provides too.

* Tue Apr 03 2018 Josh Stone <jistone@redhat.com> - 1.25.0-1
- Update to 1.25.0.
- Add rustfmt-preview as a subpackage.

* Thu Feb 22 2018 Josh Stone <jistone@redhat.com> - 1.24.0-1
- Update to 1.24.0.

* Tue Jan 16 2018 Josh Stone <jistone@redhat.com> - 1.23.0-2
- Rebuild without bootstrap binaries.

* Mon Jan 15 2018 Josh Stone <jistone@redhat.com> - 1.23.0-1
- Bootstrap 1.23 on el8.
