FaiRTT variant for the supplied ns-3 TcpBbr implementation
==========================================================

Files
-----
tcp-bbr-fairtt.cc / tcp-bbr-fairtt.h define a separate congestion-control
class, ns3::TcpBbrFairtt. The original tcp-bbr.cc and tcp-bbr.h are not
replaced.

Important research note
----------------------
The implementation follows Algorithm 1 and the equations as transcribed in
the uploaded FaiRTT paper: PROBE_BW-only adjustment, gamma discount, beta
weighting, distinct min-RTT values, and Wt=min(receive window, congestion
window). However, the paper's printed equations (5)-(7) are dimensionally
ambiguous (RTT values are combined with a window-size denominator). This
implementation preserves the printed formula's structure; validate the
interpretation with the paper authors/advisor before describing it as a
faithful reproduction. This is a source-level implementation only; it has
not been compiled against the user's full ns-3 checkout in this environment.

Install
-------
1. Back up your ns-3 checkout first:
   cp -a ~/ns-3-dev/src/internet/model/tcp-bbr.cc ~/ns-3-dev/src/internet/model/tcp-bbr.cc.bak
   cp -a ~/ns-3-dev/src/internet/model/tcp-bbr.h  ~/ns-3-dev/src/internet/model/tcp-bbr.h.bak
2. Copy tcp-bbr-fairtt.cc and tcp-bbr-fairtt.h into:
   ~/ns-3-dev/src/internet/model/
3. Edit ~/ns-3-dev/src/internet/CMakeLists.txt and add
   model/tcp-bbr-fairtt.cc to the same source list that contains model/tcp-bbr.cc,
   and model/tcp-bbr-fairtt.h to the corresponding header list if that list is
   explicit. Keep original BBR entries.
4. Build from ~/ns-3-dev:
   ./ns3 configure --enable-examples --enable-tests
   ./ns3 build
5. Do not change the topology yet. First confirm the class builds. Then select
   ns3::TcpBbrFairtt in the topology's TCP congestion-control TypeId setting,
   rerun a small test, and compare against the unchanged baseline BBR run.

Attributes
----------
FairRttBeta  default 0.8
FairRttGamma default 0.99

Validation checklist
--------------------
- Confirm CMake includes the new source file.
- Confirm build succeeds without changing original BBR files.
- Confirm a simulation can instantiate ns3::TcpBbrFairtt.
- Log current state, lastRTT, alpha, BDP before/after scaling to validate the
  trigger and ensure values are sensible.
- Compare baseline and FaiRTT with identical topology, seeds, and traffic.
