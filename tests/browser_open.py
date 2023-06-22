import webbrowser
import sys

port = sys.argv[1]

IP = "127.0.0.1"

req_url = f"http://{IP}:{port}"


def starttab(uri):
    webbrowser.open_new_tab(uri)


def main():
    starttab(req_url + "/http.txt")
    starttab(req_url + "/audio.mp3")
    starttab(req_url + "/index.html")
    starttab(req_url + "/sample.pdf")
    starttab(req_url + "/test.txt")
    starttab(req_url + "/http.txt")
    starttab(req_url + "/linux.gif")
    starttab(req_url + "/image.jpeg")
    starttab(req_url + "/img.png")
    starttab(req_url + "/photo.jpg")
    starttab(req_url + "/video.mp4")
    starttab(req_url + "/sample.json")
    starttab(req_url + "/file.pp")


if __name__ == "__main__":
    main()
