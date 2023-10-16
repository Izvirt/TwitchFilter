from twitchAPI.twitch import Twitch
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException, status, Header
from yaml.loader import SafeLoader
from fastapi_utils.tasks import repeat_every
from typing import Annotated
import uvicorn
import yaml


@dataclass
class Tag:
    label: str
    keywords: list


@dataclass
class Data:
    label: str
    keywords: list
    streams: list


@dataclass
class Channel:
    streamname: str
    username: str
    viewers: int
    streamstarted: str
    thumbnail: str
    gameid: int


with open('config.yaml', encoding="utf-8") as f:
    config = yaml.load(f, Loader=SafeLoader)
with open('apikeys.yaml', encoding="utf-8") as f:
    apikeys = yaml.load(f, Loader=SafeLoader)
app_id = apikeys.get('twitchAPI').get('appKey')
app_secret = apikeys.get('twitchAPI').get('secretKey')
app = FastAPI()
app.state.gathereddata = []
game = str(config.get('game'))
for tag in config.get('streams'):
    app.state.gathereddata.append(Data(tag.get('label'), tag.get('keywords'), []))


@app.on_event('startup')
@repeat_every(seconds=60)
async def twitchsearch():
    twitch = await Twitch(app_id, app_secret)
    # Запрос на вытаскивание всех каналов по одной игре из конфига
    twchannels = []
    async for stream in twitch.get_streams(first=100,
                                           game_id=game,
                                           stream_type='live'):
        twchannels.append(Channel(str(stream.title),
                                  str(stream.user_name),
                                  int(stream.viewer_count),
                                  str(stream.started_at),
                                  str(stream.thumbnail_url),
                                  int(stream.game_id)))
    await twitch.close()
    # Происходит сортировка по каждому label из конфига. tag - один элемент из списка.
    for tag in app.state.gathereddata:
        newchannellist = []
        for channel in twchannels:
            for keyword in tag.keywords:
                if channel.streamname.find(keyword) != -1:
                    newchannellist.append(channel)
                    break
        tag.streams = newchannellist


@app.get("/")
async def getchannels(key: Annotated[str | None, Header()] = None):
    if key != apikeys.get('filterAPI').get('readKey'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect key",
        )
    return app.state.gathereddata


@app.post("/add/")
async def addtag(key: Annotated[str | None, Header()] = None, req: Tag = None):
    if key != apikeys.get('filterAPI').get('writeKey'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect key",
        )
    # Проверка на попытку дублирования тэга
    for tag in app.state.gathereddata:
        if tag.label == req.label:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Already exist"
            )
    # Добавление в память приложения
    app.state.gathereddata.append(Data(req.label, req.keywords, []))
    # Добавление в config.yaml
    config.get('streams').append(dict([('label', req.label), ('keywords', req.keywords)]))
    with open('config.yaml', 'w', encoding="utf-8") as fw:
        yaml.dump(config, fw, sort_keys=False, allow_unicode=True, encoding="utf-8", default_flow_style=False)
    return {"added": True}


@app.delete("/del/")
async def deltag(key: Annotated[str | None, Header()] = None, req: str = None):
    if key != apikeys.get('filterAPI').get('writeKey'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect key",
        )
    for tag in app.state.gathereddata:
        if tag.label == req:
            app.state.gathereddata.remove(tag)
            for element in config.get('streams'):
                if element.get('label') == req:
                    config.get('streams').remove(element)
                    break
            with open('config.yaml', 'w', encoding="utf-8") as fw:
                yaml.dump(config, fw, sort_keys=False, allow_unicode=True, encoding="utf-8",
                          default_flow_style=False)
            return {"deleted": True}
    return {"deleted": False}


@app.on_event("shutdown")
async def saveyaml():
    with open('config.yaml', 'w', encoding="utf-8") as fw:
        yaml.dump(config, fw, sort_keys=False, allow_unicode=True, encoding="utf-8", default_flow_style=False)


if __name__ == "__main__":
    uvicorn.run(app, host="192.168.1.111", port=8000)
