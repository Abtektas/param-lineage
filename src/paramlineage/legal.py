# SPDX-License-Identifier: BSD-3-Clause
"""The licences and the notices of the project, so that every copy of the program carries them."""

from __future__ import annotations

from . import __version__

COPYRIGHT = "Copyright (c) 2026, the param-lineage contributors"

# The same text as the file LICENSE; a test compares them.
LICENSE = """\
BSD 3-Clause License

Copyright (c) 2026, the param-lineage contributors
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

# The same text as the file LICENSE-THIRD-PARTY (the LICENSE of PX4 v1.18.0-rc1); a test compares them.
LICENSE_PX4 = """\
BSD 3-Clause License

Copyright (c) 2012 - 2025, PX4 Development Team
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

NO_WARRANTY = (
    'This software is provided "as is", without warranty of any kind. The authors and '
    "contributors accept no liability and no responsibility for any use of it or of its results."
)

INFORMATION_ONLY = (
    "param-lineage describes how PX4 parameters changed between releases. It is not a safety "
    "assessment and does not say which values are safe to fly. Data that has not been checked "
    "is marked as such, and a check that lists nothing does not mean a configuration is right. "
    "Whether and how you use it and its results is your own decision, at your own risk."
)

PX4_DATA = (
    "The parameter data (names, descriptions, defaults, ranges, enum values and conversions) "
    "comes from the PX4 Autopilot project, copyright (c) 2012 - 2025, PX4 Development Team, "
    "licensed under the BSD 3-Clause license; its text is in the file LICENSE-THIRD-PARTY."
)

TRADEMARK = (
    "This project is not affiliated with or endorsed by the PX4 project or the Dronecode "
    "Foundation. PX4 is a trademark of Dronecode Project, Inc. It is used here only to name the "
    "software this project describes."
)


def license_text() -> str:
    """What "param-lineage license" prints: both license texts in full."""
    return "\n".join(
        [
            "param-lineage:",
            "",
            LICENSE,
            "PX4 Autopilot (the parameter data):",
            "",
            LICENSE_PX4,
            TRADEMARK,
        ]
    )


def version_text() -> str:
    """What --version prints: the version, and the terms in short."""
    return "\n".join(
        [
            f"param-lineage {__version__}",
            COPYRIGHT,
            'License: BSD-3-Clause. "param-lineage license" prints the full texts.',
            NO_WARRANTY,
            INFORMATION_ONLY,
            PX4_DATA,
            TRADEMARK,
        ]
    )
