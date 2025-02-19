/*
 * Copyright The NOMAD Authors.
 *
 * This file is part of NOMAD. See https://nomad-lab.eu for further info.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
import React from 'react'
import { renderNoAPI } from '../conftest.spec'
import { expectPlot, VisualizationState } from './conftest.spec'
import RadiusOfGyration, { rgError } from './RadiusOfGyration'

test.each([
  ['no data', VisualizationState.NoData, {molecular: false}, undefined],
  ['loading', VisualizationState.Loading, {molecular: undefined}, 'radius-of-gyration-molecular-0-placeholder'],
  ['error: data cannot be false', VisualizationState.Error, false, undefined],
  ['error: data cannot be undefined', VisualizationState.Error, undefined, undefined],
  ['error: invalid data layout', VisualizationState.Error, {invalid: "data"}, undefined],
  ['valid', VisualizationState.Success, {molecular: [{label: 'MOL', time: [0, 1], value: [0, 1]}]}, undefined]
])('rg plot: %s', async (id, state, data, placeholderTestID) => {
  renderNoAPI(<RadiusOfGyration rg={data} />)
  await expectPlot(state, placeholderTestID, rgError)
})
